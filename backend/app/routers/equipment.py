from fastapi import APIRouter, Depends, Query
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_permission
from app.core.roles import Permission
from app.models.enums import EquipmentOperationalStatus, EquipmentStatus
from app.models.equipment import Equipment, EquipmentRequest
from app.schemas.equipment import EquipmentCatalogueOut, EquipmentOption, EquipmentOut

router = APIRouter(prefix="/equipment", tags=["equipment"])


def _reserved_units_subquery():
    """Units already spoken for, per equipment item.

    Only `reserved` counts. A request that is merely `requested` or
    `reviewing` has not been granted yet, and `rejected`/`cancelled` ones
    never will be -- counting any of those would hide stock that is in
    fact free, and Technical Support would turn down events they could
    actually support.
    """
    return (
        select(
            EquipmentRequest.equipment_id.label("equipment_id"),
            func.coalesce(func.sum(EquipmentRequest.quantity_requested), 0).label("reserved"),
        )
        .where(EquipmentRequest.status == EquipmentStatus.reserved)
        .group_by(EquipmentRequest.equipment_id)
        .subquery()
    )


def _available_quantity(item: Equipment, reserved: int) -> int:
    """How many units can actually be used for an event.

    An item that is not operational reports 0 regardless of the
    arithmetic: two damaged mixers are not two available mixers. The Week 1
    briefing is explicit that equipment recorded as unavailable must not be
    treated as freely available.

    Clamped at 0 so over-reservation (more reserved than owned, possible if
    stock is reduced after the fact) reports "none left" rather than a
    negative count.
    """
    if item.operational_status is not EquipmentOperationalStatus.available:
        return 0
    return max(item.total_quantity - reserved, 0)


def _to_out(item: Equipment, reserved: int) -> EquipmentOut:
    """Build one catalogue row.

    Written out field by field rather than validated straight off the ORM
    object: `available_quantity` is computed, not stored, so there is no
    attribute on the model to read it from.
    """
    return EquipmentOut(
        id=item.id,
        name=item.name,
        category=item.category,
        description=item.description,
        total_quantity=item.total_quantity,
        location=item.location,
        operational_status=item.operational_status,
        available_quantity=_available_quantity(item, reserved),
        technical_specs=item.technical_specs,
    )


def _apply_filters(stmt: Select, type_: str | None, q: str | None) -> Select:
    """Narrow the catalogue by type and/or free-text search.

    The two combine with AND -- picking "Audio" and typing "mic" means
    audio items matching "mic", not everything audio plus everything
    matching "mic".

    `ilike` is used rather than lowercasing by hand; SQLAlchemy renders it
    as `lower(a) LIKE lower(b)` on backends without ILIKE, so the tests
    (SQLite) and production (Postgres) agree.
    """
    if type_:
        stmt = stmt.where(Equipment.category == type_)
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Equipment.name.ilike(pattern),
                Equipment.description.ilike(pattern),
            )
        )
    return stmt


# Declared before the catalogue route for readability only -- "options" is a
# literal path, not a parameter, so there is no capture to worry about.
@router.get("/options", response_model=list[EquipmentOption])
def list_equipment_options(
    q: str | None = Query(None, description="Free-text search over name and description."),
    db: Session = Depends(get_db),
    _: object = Depends(require_permission(Permission.EVENT_WRITE)),
) -> list[EquipmentOption]:
    """Pickable equipment, for the picker on an event request form.

    Gated on EVENT_WRITE rather than EQUIPMENT_READ on purpose. The
    justification for an Event Organiser reaching this data is "you are
    filling in an event request", not "you may browse our inventory" -- and
    EQUIPMENT_READ is the permission that means the latter. A Coordinator
    holds EVENT_WRITE too, so the same picker works on their screens.

    Retired items are excluded: they are permanently withdrawn, so offering
    one would guarantee a request nobody can fulfil. Damaged and
    under-maintenance items stay, because repairs finish and the event may
    be months away -- whether the kit can actually be provided on the day is
    Technical Support's call, not this form's.
    """
    stmt = select(Equipment).where(
        Equipment.operational_status != EquipmentOperationalStatus.retired
    )
    stmt = _apply_filters(stmt, None, q).order_by(Equipment.category, Equipment.name)
    return [EquipmentOption.model_validate(item) for item in db.execute(stmt).scalars()]


@router.get("", response_model=EquipmentCatalogueOut)
def list_equipment(
    type: str | None = Query(None, description="Exact equipment type (category) to filter by."),
    q: str | None = Query(None, description="Free-text search over name and description."),
    db: Session = Depends(get_db),
    _: object = Depends(require_permission(Permission.EQUIPMENT_READ)),
) -> EquipmentCatalogueOut:
    """The full equipment catalogue, optionally filtered.

    Gated on EQUIPMENT_READ rather than on the tech_support role. The
    permission is the real rule -- Coordinators hold it too, because they
    have to know what exists before requesting it -- and gating on the role
    would mean rewriting this endpoint the moment a second role needs it.

    Items that are damaged, under maintenance or retired are still LISTED.
    "Every item held by ConnectSphere" means every item; whether a given
    one can be used is what `operational_status` and `available_quantity`
    are for. Hiding them would leave Technical Support unable to see the
    kit they most need to know about.
    """
    reserved = _reserved_units_subquery()

    stmt = (
        select(Equipment, func.coalesce(reserved.c.reserved, 0))
        .outerjoin(reserved, reserved.c.equipment_id == Equipment.id)
        .order_by(Equipment.category, Equipment.name)
    )
    rows = db.execute(_apply_filters(stmt, type, q)).all()

    items = [_to_out(item, reserved_units) for item, reserved_units in rows]

    # Deliberately unfiltered -- see EquipmentCatalogueOut.types.
    types = [
        category
        for (category,) in db.execute(
            select(Equipment.category)
            .where(Equipment.category.is_not(None))
            .distinct()
            .order_by(Equipment.category)
        ).all()
    ]

    return EquipmentCatalogueOut(items=items, types=types)
