from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import (
    auth,
    coordinators,
    equipment,
    events,
    health,
    notifications,
    registrations,
    users,
    venue_bookings,
    venues,
)

import app.models  # noqa: F401  (registers models on Base.metadata)

app = FastAPI(title="Spm2026 API")

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
app.include_router(coordinators.router)
app.include_router(notifications.router)
app.include_router(equipment.router)
app.include_router(users.router)
app.include_router(registrations.router)
app.include_router(venues.router)
app.include_router(venue_bookings.router)
