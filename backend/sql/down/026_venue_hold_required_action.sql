-- Undo sql/026_venue_hold_required_action.sql. Drops every hold's required action.

alter table public.venue_bookings drop column if exists hold_action;
