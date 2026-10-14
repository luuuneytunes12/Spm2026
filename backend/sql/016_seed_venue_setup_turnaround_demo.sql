-- Run in the Supabase SQL editor, after 015. Safe to re-run (idempotent).
--
-- Demo values for "Filter Venues by Date and Time". Every venue starts at 0
-- setup and 0 turnaround minutes (sql/015), which changes nothing; these
-- give three seeded venues realistic values so the effect can be seen.
--
--   Harbourfront Seminar Room 2   30 min setup,  60 min turnaround
--   Marina Grand Ballroom        120 min setup,  90 min turnaround
--   Suntec Exhibition Hall 3     240 min setup, 180 min turnaround
--
-- Harbourfront has the approved booking from sql/012 (8 Oct 2026,
-- 16:46-19:46 Singapore time). With 60 minutes to reset after it and 30 to
-- set up before the next event, it is not free again for an event until
-- 21:16 -- so a search for 8 Oct 21:00-23:00 still leaves it out, and one
-- for 21:30-23:00 shows it. Rows are found by name; a missing venue is
-- simply skipped.

update public.venues v
set setup_minutes = d.setup_minutes,
    turnaround_minutes = d.turnaround_minutes
from (values
    ('Harbourfront Seminar Room 2', 30, 60),
    ('Marina Grand Ballroom', 120, 90),
    ('Suntec Exhibition Hall 3', 240, 180)
) as d(name, setup_minutes, turnaround_minutes)
where v.name = d.name;

-- Verify:
select name, setup_minutes, turnaround_minutes
from public.venues
where setup_minutes > 0 or turnaround_minutes > 0
order by name;
