-- Undo sql/026_requirement_unavailable_reason.sql. The reasons recorded for
-- Unavailable requirements are lost; the requirements and their statuses stay.

alter table public.coordinator_equipment_requirements
    drop column if exists unavailable_reason;
