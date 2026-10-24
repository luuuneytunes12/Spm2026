import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.error_handlers import register_error_handlers
from app.routers import (
    auth,
    clarifications,
    coordinator_lead,
    coordinators,
    equipment,
    equipment_requirements,
    equipment_reservations,
    events,
    health,
    notifications,
    registrations,
    safety_checks,
    users,
    venue_bookings,
    venue_catalogue,
    venues,
)

import app.models  # noqa: F401  (registers models on Base.metadata)
from app.services.hold_sweeper import HoldSweeper


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Run the tentative-hold sweeper (reminders and expiry) while the app is up."""
    task = None
    if settings.hold_sweep_interval_seconds > 0:
        sweeper = HoldSweeper(SessionLocal, settings.hold_sweep_interval_seconds)
        task = asyncio.create_task(sweeper.run_forever())
    yield
    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="Spm2026 API", lifespan=lifespan)

register_error_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(events.router)
app.include_router(clarifications.router)
app.include_router(coordinators.router)
app.include_router(coordinator_lead.router)
app.include_router(notifications.router)
app.include_router(equipment.router)
app.include_router(equipment_requirements.router)
app.include_router(equipment_reservations.router)
app.include_router(users.router)
app.include_router(registrations.router)
# Before venues: its static GET /venues/activity must win over /venues/{venue_id}.
app.include_router(venue_catalogue.router)
app.include_router(venues.router)
app.include_router(venue_bookings.router)
app.include_router(safety_checks.router)
