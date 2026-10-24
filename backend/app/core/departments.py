"""The departments internal staff can belong to.

Mirrored (identical string values) in `frontend/src/lib/departments.ts`. A
small, fixed list: a staff member picks one, they never type their own.
"""

from enum import StrEnum


class Department(StrEnum):
    EVENTS_COORDINATION = "events_coordination"
    VENUE_OPERATIONS = "venue_operations"
    TECHNICAL_SUPPORT = "technical_support"
    SAFETY_COMPLIANCE = "safety_compliance"


# Presentable names; used by the UI, never compared against or stored.
DEPARTMENT_LABELS: dict[Department, str] = {
    Department.EVENTS_COORDINATION: "Events Coordination",
    Department.VENUE_OPERATIONS: "Venue Operations",
    Department.TECHNICAL_SUPPORT: "Technical Support",
    Department.SAFETY_COMPLIANCE: "Safety & Compliance",
}

MAX_RESPONSIBILITIES_LENGTH = 1000
