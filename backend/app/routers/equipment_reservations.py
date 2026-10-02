from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.datetimes import as_utc
from app.core.db import get_db
from app.core.deps import require_role
from app.core.roles import Role
from app.models.enums import PLANNED_EVENT_STATUSES, EquipmentStatus
from app.models.equipment import Equipment, EquipmentRequest
from app.models.events import Event
from app.models.user import User
from app.schemas.equipment_reservation import (
    EquipmentAvailabilityOut,
    EquipmentReservationCreate,
    EquipmentReservationOut,
    ReservableEvent,
)
from app.services.equipment_availability import available_quantity, reserved_units

router = APIRouter(prefix="/equipment-reservations", tags=["equipment-reservations"])

# Gated on the role, not on EQUIPMENT_MANAGE. Both stories are Technical
# Support's, and the Organiser -- an external client, who holds every
# permission as the admin-equivalent -- must not see stock levels or commit
# stock (see EquipmentOption for the same boundary on the request form).
_tech_support = require_role(Role.TECH_SUPPORT)

# A line still waiting on Technical Support. `reserved` is already done;
# `rejected` and `cancelled` are closed.
_RESERVABLE_LINE_STATUSES = (EquipmentStatus.requested, EquipmentStatus.reviewing)


def _reject(field: str, message: str) -> None:
    """A 422 in FastAPI's own shape, naming the query parameter at fault."""
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=[{"loc": ["query", field], "msg": message}],
    )


def _get_event(db: Session, event_id: int) -> Event:
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


def _out(line: EquipmentRequest) -> EquipmentReservationOut:
    event = line.event
    return EquipmentReservationOut(
        id=line.id,
        event=event,
        equipment_id=line.equipment_id,
        equipment_name=line.equipment_name,
        equipment_category=line.equipment_category,
        quantity=line.quantity_requested,
        start_time=event.proposed_start,
        end_time=event.proposed_end,
        reserved_by=line.reviewed_by_user,
        reserved_at=line.reviewed_at,
    )


@router.get("/events", response_model=list[ReservableEvent])
def list_reservable_events(
    db: Session = Depends(get_db),
    _: User = Depends(_tech_support),
) -> list[Event]:
    """Events equipment can be reserved for, soonest first, each with the
    equipment it asked for.

    Approved and not yet finished, and with a date and time -- without one
    there is no window to check availability against.
    """
    return list(
        db.scalars(
            select(Event)
            .where(
                Event.status.in_(PLANNED_EVENT_STATUSES),
                Event.proposed_start.is_not(None),
                Event.proposed_end.is_not(None),
            )
            .order_by(Event.proposed_start, Event.id)
        )
    )


@router.get("/availability", response_model=EquipmentAvailabilityOut)
def check_availability(
    equipment_id: int = Query(..., description="The catalogue item to check."),
    start: datetime = Query(..., description="Start of the window, ISO 8601."),
    end: datetime = Query(..., description="End of the window, ISO 8601."),
    event_id: int | None = Query(
        None, description="Compare against what this event asked for."
    ),
    db: Session = Depends(get_db),
    _: User = Depends(_tech_support),
) -> EquipmentAvailabilityOut:
    """How many units of one item are free for [start, end).

    Units reserved for ANY event whose window overlaps are not counted as
    available. Given an event that asked for this item, the result also says
    whether what is free covers what it requires.
    """
    window_start, window_end = as_utc(start), as_utc(end)
    if window_end <= window_start:
        _reject("end", "The end must be after the start.")

    item = db.get(Equipment, equipment_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Equipment not found")

    reserved = reserved_units(db, item.id, window_start, window_end)
    available = available_quantity(item, reserved)

    required = None
    if event_id is not None:
        event = _get_event(db, event_id)
        required = db.scalar(
            select(EquipmentRequest.quantity_requested).where(
                EquipmentRequest.event_id == event.id,
                EquipmentRequest.equipment_id == item.id,
            )
        )

    return EquipmentAvailabilityOut(
        equipment_id=item.id,
        equipment_name=item.name,
        equipment_category=item.category,
        operational_status=item.operational_status,
        total_quantity=item.total_quantity,
        reserved_quantity=reserved,
        available_quantity=available,
        start_time=window_start,
        end_time=window_end,
        required_quantity=required,
        sufficient=None if required is None else available >= required,
    )


@router.post("", response_model=EquipmentReservationOut)
def reserve_equipment(
    body: EquipmentReservationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(_tech_support),
) -> EquipmentReservationOut:
    """Reserve one item for an event, for the event's date and time.

    If the event requested the item, its request is what gets reserved, all
    or nothing: if fewer units are free than it asked for, the reservation
    is refused and the error says how many are available. If it did not,
    Technical Support adds the item with a quantity of their own, recorded
    as a request already reserved by them.

    The item's row is locked before availability is read, so two
    reservations for overlapping events cannot both see the same free units
    and overcommit them: the second waits, then sees the first.
    """
    event = _get_event(db, body.event_id)
    if event.status not in PLANNED_EVENT_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Equipment can only be reserved once the event is approved; it is '{event.status}'.",
        )
    if event.proposed_start is None or event.proposed_end is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The event has no date and time to reserve equipment for.",
        )

    item = db.get(Equipment, body.equipment_id, with_for_update=True)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="That equipment does not exist.",
        )

    line = db.scalar(
        select(EquipmentRequest).where(
            EquipmentRequest.event_id == event.id,
            EquipmentRequest.equipment_id == item.id,
        )
    )
    if line is None:
        # Not on the event's request: Technical Support is adding it, so they
        # say how many.
        if body.quantity is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"This event has not requested {item.name}; enter a quantity to reserve.",
            )
        quantity = body.quantity
    else:
        if line.status is EquipmentStatus.reserved:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"{item.name} is already reserved for this event.",
            )
        if line.status not in _RESERVABLE_LINE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"This request for {item.name} is {line.status} and cannot be reserved.",
            )
        # All or nothing: what the event asked for is what gets reserved.
        if body.quantity is not None and body.quantity != line.quantity_requested:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"This event requested {line.quantity_requested} {item.name}; reserve that quantity.",
            )
        quantity = line.quantity_requested

    available = available_quantity(
        item, reserved_units(db, item.id, event.proposed_start, event.proposed_end)
    )
    if quantity > available:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Only {available} {item.name} available for this event's date and time; "
                f"{quantity} requested."
            ),
        )

    if line is None:
        line = EquipmentRequest(event_id=event.id, equipment_id=item.id, quantity_requested=quantity)
        db.add(line)
    line.status = EquipmentStatus.reserved
    line.reviewed_by = user.id
    line.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(line)
    return _out(line)


@router.get("", response_model=list[EquipmentReservationOut])
def list_event_reservations(
    event_id: int = Query(..., description="The event whose reservations to list."),
    db: Session = Depends(get_db),
    _: User = Depends(_tech_support),
) -> list[EquipmentReservationOut]:
    """The equipment reserved for one event."""
    event = _get_event(db, event_id)
    lines = db.scalars(
        select(EquipmentRequest)
        .options(joinedload(EquipmentRequest.reviewed_by_user))
        .where(
            EquipmentRequest.event_id == event.id,
            EquipmentRequest.status == EquipmentStatus.reserved,
        )
        .order_by(EquipmentRequest.id)
    ).unique()
    return [_out(line) for line in lines]
