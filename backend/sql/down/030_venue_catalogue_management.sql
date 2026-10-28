drop index if exists public.uq_venues_name_lower;
alter table public.venue_bookings drop column if exists review_reason;
alter table public.venue_bookings drop column if exists review_flagged_at;
drop table if exists public.venue_activity;
