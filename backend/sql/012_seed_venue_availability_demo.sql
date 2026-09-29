-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- Demo data for the date and time filter of "Search and Filter Venues".
--
-- Nothing in the app writes venue_bookings or venue_unavailability yet --
-- Venue Booking Request/Approval and venue blocking are separate stories --
-- so without these rows the date filter is fully tested but never visibly
-- hides a venue. One row in each table:
--
--   * an APPROVED booking of Harbourfront Seminar Room 2 (holds 80) for
--     "Registration Test Event" (confirmed, 50 attendees). Its time is taken
--     from the event's own proposed start and end rather than typed here,
--     so booking and event cannot disagree (W4 p5: reservations "should
--     reflect the date and time of the corresponding event"). Requested by
--     Ercong, a Coordinator -- the event has none assigned -- and approved
--     by Edric, Venue Staff.
--
--   * a maintenance block on Raffles Place Training Studio (holds 50) over
--     the same window.
--
-- Searching that window therefore hides both venues; any other window
-- shows them. Rows are found by name and email, not id, and nothing is
-- inserted if any of them is missing.

insert into public.venue_bookings
    (event_id, venue_id, requested_by, reviewed_by, start_time, end_time, status, reviewed_at)
select e.id, v.id, coordinator.id, staff.id, e.proposed_start, e.proposed_end,
       'approved', now()
from public.events e
join public.users organiser on organiser.id = e.organiser_id
join public.venues v on v.name = 'Harbourfront Seminar Room 2'
join public.users coordinator on coordinator.email = 'event_coord@cs.local'
join public.users staff on staff.email = 'ven_staff@cs.local'
where e.name = 'Registration Test Event'
  and organiser.email = 'event_org@cs.local'
  and e.proposed_start is not null
  and e.proposed_end is not null
  and not exists (
      select 1 from public.venue_bookings b
      where b.event_id = e.id and b.venue_id = v.id
  );

insert into public.venue_unavailability (venue_id, start_time, end_time, reason, created_by)
select v.id, e.proposed_start, e.proposed_end, 'Scheduled maintenance', staff.id
from public.events e
join public.users organiser on organiser.id = e.organiser_id
join public.venues v on v.name = 'Raffles Place Training Studio'
join public.users staff on staff.email = 'ven_staff@cs.local'
where e.name = 'Registration Test Event'
  and organiser.email = 'event_org@cs.local'
  and e.proposed_start is not null
  and e.proposed_end is not null
  and not exists (
      select 1 from public.venue_unavailability u
      where u.venue_id = v.id
        and u.start_time = e.proposed_start
        and u.end_time = e.proposed_end
  );

-- Verify:
select 'booking' as kind, v.name as venue, b.status::text as status, b.start_time, b.end_time
from public.venue_bookings b join public.venues v on v.id = b.venue_id
union all
select 'block', v.name, u.reason, u.start_time, u.end_time
from public.venue_unavailability u join public.venues v on v.id = u.venue_id
order by 1, 2;
