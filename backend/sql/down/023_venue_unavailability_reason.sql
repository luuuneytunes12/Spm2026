-- Undo sql/023_venue_unavailability_reason.sql. The reason category and the
-- last-edited-by/at values are lost; the periods and their details stay.

alter table public.venue_unavailability drop constraint if exists venue_unavailability_reason_category_check;
alter table public.venue_unavailability
    drop column if exists reason_category,
    drop column if exists updated_by,
    drop column if exists updated_at;
