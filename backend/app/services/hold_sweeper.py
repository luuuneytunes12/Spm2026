"""The background job that keeps tentative holds on time.

Every `hold_sweep_interval_seconds` it reminds Coordinators whose holds are
about to expire and expires the holds whose time has passed -- so both happen
when they are due, not only the next time somebody opens a venue page.

`HoldSweeper.run_once` does one pass in its own database session and is what
the tests call; `run_forever` repeats it on the app's event loop, doing the
database work in a worker thread so it never blocks requests. Started and
stopped by the app's lifespan (app/main.py); an interval of 0 turns it off.
"""

import asyncio
import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.services.venue_holds import expire_tentative_holds, send_hold_reminders

logger = logging.getLogger(__name__)


class HoldSweeper:
    def __init__(
        self, session_factory: Callable[[], AbstractContextManager[Session]], interval_seconds: int
    ) -> None:
        self.session_factory = session_factory
        self.interval_seconds = interval_seconds

    def run_once(self, now: datetime | None = None) -> tuple[int, int]:
        """One pass: (reminded, expired). A hold already past its expiry is
        expired and told so; it is never also reminded."""
        current = now or datetime.now(timezone.utc)
        with self.session_factory() as db:
            expired = expire_tentative_holds(db, current)
            reminded = send_hold_reminders(db, current)
        return reminded, expired

    async def run_forever(self) -> None:
        while True:
            try:
                await asyncio.to_thread(self.run_once)
            except Exception:  # keep sweeping; one bad pass must not stop it
                logger.exception("Tentative hold sweep failed.")
            await asyncio.sleep(self.interval_seconds)
