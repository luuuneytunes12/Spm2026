-- Undo sql/021_venue_setup_turnaround.sql. The recorded setup/turnaround
-- minutes are lost; every venue goes back to "no buffer".

alter table public.venues
    drop constraint if exists venues_setup_minutes_check,
    drop constraint if exists venues_turnaround_minutes_check,
    drop column if exists setup_minutes,
    drop column if exists turnaround_minutes,
    drop column if exists setup_turnaround_updated_by,
    drop column if exists setup_turnaround_updated_at;
