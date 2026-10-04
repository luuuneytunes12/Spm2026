"""The production ReservationGateway: Ercong's Equipment Reservations.

Lives beside the other services rather than in the domain because it has to
import his router -- his reservation rules are written inside a route
function, and this adapter is the one place that reaches for it. The domain
sees only the ReservationGateway contract.

His code is used as it is. Nothing here changes it, copies its stock or
overlap arithmetic, or relies on anything of his beyond the signature pinned
by tests/test_requirement_reservation_atomicity.py.
"""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.equipment_fulfillment import ReservationGateway, ReservationRefused
from app.models.equipment import EquipmentRequest
from app.models.user import User
from app.routers.equipment_reservations import (
    _RESERVABLE_LINE_STATUSES,
    reserve_equipment,
)
from app.schemas.equipment_reservation import EquipmentReservationCreate


class ErcongReservationGateway(ReservationGateway):
    """Reserves through the existing Equipment Reservations function.

    `reserve_equipment` is called as it is: it does the stock check, the
    overlap check and the write, and it COMMITS the session itself. That one
    commit is what writes a pending link with it, in one transaction -- so
    this method must be called with the link already added, and never
    followed by a second commit that matters. (Proved in
    tests/test_requirement_reservation_atomicity.py.)

    His function speaks HTTP -- it raises HTTPException. The domain does not,
    so the refusal is translated here, keeping his status and his words.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def forced_quantity(self, event_id: int, equipment_id: int) -> int | None:
        """His rule: an item the Organiser asked for is reserved at THEIR
        quantity, whole. Only while that line can still be reserved; for any
        other state his own refusal is the right thing to show."""
        line = self._db.scalar(
            select(EquipmentRequest).where(
                EquipmentRequest.event_id == event_id,
                EquipmentRequest.equipment_id == equipment_id,
            )
        )
        if line is None or line.status not in _RESERVABLE_LINE_STATUSES:
            return None
        return line.quantity_requested

    def reserve(
        self, *, event_id: int, equipment_id: int, quantity: int | None, user: User
    ) -> int:
        try:
            reservation = reserve_equipment(
                body=EquipmentReservationCreate(
                    event_id=event_id, equipment_id=equipment_id, quantity=quantity
                ),
                db=self._db,
                user=user,
            )
        except HTTPException as refusal:
            raise ReservationRefused(
                _words(refusal.detail), status_code=refusal.status_code
            ) from refusal
        return reservation.quantity


def _words(detail: object) -> str:
    """His refusal's message, whether it came as text or as a list."""
    if isinstance(detail, list):
        return " ".join(str(item.get("msg", item)) if isinstance(item, dict) else str(item) for item in detail)
    return str(detail)
