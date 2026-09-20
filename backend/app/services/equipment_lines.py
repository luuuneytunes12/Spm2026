"""Writing an event's equipment line-items.

Like app/services/assignment.py, nothing here commits. The router owns the
transaction, so an event and its equipment lines are written together or not
at all.
"""

from collections import Counter

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import EquipmentOperationalStatus
from app.models.equipment import Equipment, EquipmentRequest
from app.models.events import Event
from app.schemas.event import EquipmentLineIn

# Every rejection below is reported against the whole block rather than an
# individual row.
#
# The frontend flattens a 422's `loc` into a dotted string and matches it
# against its field names, so ["body", "equipment_items", 0, "equipment_id"]
# would arrive as "equipment_items.0.equipment_id" and match nothing --
# the error would render as a banner with no field marked. Flagging the
# block keeps the existing error plumbing working, and these are all errors
# the form should have prevented anyway: a person cannot pick a duplicate,
# a retired item, or a nonexistent id through the picker.
_LOC = ["body", "equipment_items"]


def _reject(message: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=[{"loc": _LOC, "msg": message}],
    )


def _validate(db: Session, lines: list[EquipmentLineIn]) -> None:
    """Refuse anything the database would otherwise refuse less politely.

    `equipment_requests.equipment_id` is ON DELETE RESTRICT and the table
    carries a unique constraint on (event_id, equipment_id), so an unknown
    id or a repeated one would surface as an IntegrityError -- a 500 with a
    Postgres message in it. Checked here so the caller gets a 422 that says
    what is wrong.
    """
    duplicates = [eid for eid, count in Counter(line.equipment_id for line in lines).items() if count > 1]
    if duplicates:
        _reject(
            "The same equipment cannot be requested twice. "
            "Use the quantity to ask for more of one item."
        )

    requested_ids = {line.equipment_id for line in lines}
    found = {
        item.id: item
        for item in db.execute(
            select(Equipment).where(Equipment.id.in_(requested_ids))
        ).scalars()
    }

    missing = requested_ids - found.keys()
    if missing:
        _reject(f"No such equipment: {', '.join(str(i) for i in sorted(missing))}.")

    # Retired equipment is permanently withdrawn, so a request for one could
    # never be fulfilled. Damaged and under-maintenance items are NOT
    # refused: repairs finish, the event may be months away, and judging
    # whether the kit can actually be provided is Technical Support's call.
    retired = sorted(
        item.name
        for item in found.values()
        if item.operational_status is EquipmentOperationalStatus.retired
    )
    if retired:
        _reject(f"No longer available: {', '.join(retired)}.")


def replace_equipment_lines(
    db: Session, event: Event, lines: list[EquipmentLineIn]
) -> None:
    """Make `event`'s equipment lines exactly `lines`. Does not commit.

    A replace rather than a merge: the form always sends the full current
    list, so anything absent from it has been removed by the Organiser.
    `Event.equipment_items` is configured delete-orphan, so assigning the
    new list is enough for SQLAlchemy to delete the old rows.

    New rows take the model default status `requested`. That matters beyond
    this function: GET /equipment subtracts only `reserved` units when it
    reports availability, so asking for equipment never silently reduces the
    stock other events are offered. Granting it is Technical Support's job.
    """
    _validate(db, lines)

    # Cleared and flushed BEFORE the new rows are attached, in two steps
    # rather than one assignment.
    #
    # (event_id, equipment_id) is unique, and SQLAlchemy's unit of work
    # emits INSERTs for a table before DELETEs for it. So a one-step
    # replace that keeps an item and only changes its quantity -- "actually
    # make that 3", the most ordinary edit there is -- would insert the new
    # row while the old one was still present, and the constraint would
    # reject it. Flushing the removals first means the table is empty of
    # this event's lines by the time the inserts run.
    event.equipment_items = []
    db.flush()

    event.equipment_items = [
        EquipmentRequest(
            equipment_id=line.equipment_id,
            quantity_requested=line.quantity_requested,
            technical_requirements=line.technical_requirements,
        )
        for line in lines
    ]
