-- Demo data for local and staging databases. NEVER runs on production:
-- `supabase db push` only seeds with --include-seed, which deploy.yml does
-- not pass. Run by `supabase db reset` locally.
--
-- The seed files from backend/sql/, in the order they were written. Every
-- one is idempotent, so running this twice changes nothing. Rows that
-- reference particular users or events (012) insert nothing on a database
-- that does not have them.

-- ===== backend/sql/006_seed_equipment.sql =====

-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- Seed catalogue for the "View Equipment Catalogue" story. The equipment
-- table was empty, so there was nothing to view, filter or demonstrate.
--
-- Deliberately not all 'available': the briefing says equipment may be
-- "damaged, being repaired, or otherwise unavailable", and a catalogue
-- where every row looks identical proves nothing about the status column.
-- The maintenance/damaged/retired rows are what make the Technical Support
-- Staff view worth looking at, and what the later Equipment Availability
-- Checking story will need to exclude.
--
-- Guarded on `name` rather than ON CONFLICT: equipment has no unique
-- constraint on name, and adding one is a separate design decision (the
-- catalogue may legitimately hold two entries with the same name at
-- different locations).

insert into public.equipment
    (name, category, description, total_quantity, location, operational_status, technical_specs)
select v.name, v.category, v.description, v.total_quantity, v.location,
       v.operational_status::equipment_operational_status, v.technical_specs
from (values
    -- Projection
    ('Epson EB-L200SW Projector', 'Projection',
     'Short-throw laser projector for main halls and large rooms.',
     6, 'Marina Bay Facility - AV Store 1', 'available',
     '4000 lumens, WXGA 1280x800, HDMI x2, 16W speaker'),
    ('Portable Projection Screen 100"', 'Projection',
     'Free-standing tripod screen for rooms without a fixed screen.',
     10, 'Marina Bay Facility - AV Store 1', 'available',
     '100 inch diagonal, 16:9, matte white, tripod mount'),
    ('BenQ MW612 Projector', 'Projection',
     'Compact lamp projector for breakout rooms and workshops.',
     4, 'Jurong Facility - Store B', 'maintenance',
     '4000 lumens, WXGA, lamp replacement due'),

    -- Audio
    ('Shure BLX24 Handheld Microphone', 'Audio',
     'Wireless handheld microphone for presenters and panel sessions.',
     16, 'Marina Bay Facility - AV Store 2', 'available',
     'UHF wireless, 300ft range, rechargeable, PG58 capsule'),
    ('Sennheiser XSW-D Lapel Microphone', 'Audio',
     'Clip-on wireless microphone for keynote speakers.',
     8, 'Marina Bay Facility - AV Store 2', 'available',
     '2.4GHz digital, 250ft range, 5hr battery'),
    ('Yamaha StagePas 600BT PA System', 'Audio',
     'Portable powered PA with mixer, for outdoor and exhibition use.',
     3, 'Changi Facility - Loading Bay Store', 'available',
     '680W, 10-channel mixer, Bluetooth, two speakers'),
    ('Behringer X32 Mixing Console', 'Audio',
     'Digital mixing desk for multi-microphone conference sessions.',
     2, 'Marina Bay Facility - AV Store 2', 'damaged',
     '32-channel, 16 preamps, channel 7 fader unresponsive'),

    -- Video conferencing
    ('Logitech Rally Bar', 'Video Conferencing',
     'All-in-one video bar for hybrid events in mid-size rooms.',
     5, 'Marina Bay Facility - AV Store 1', 'available',
     '4K, 15x zoom, beamforming mics, RightSight auto-framing'),
    ('Owl Labs Meeting Owl 3', 'Video Conferencing',
     '360-degree camera and microphone for roundtable discussions.',
     6, 'Jurong Facility - Store B', 'available',
     '1080p 360 camera, 8 mic array, 18ft pickup'),
    ('Blackmagic ATEM Mini Pro', 'Video Conferencing',
     'Live switcher for streaming multi-camera sessions.',
     3, 'Marina Bay Facility - AV Store 1', 'available',
     '4x HDMI in, USB webcam out, H.264 streaming'),

    -- Lighting
    ('Godox SL-150 LED Panel', 'Lighting',
     'Continuous LED light for stage and speaker illumination.',
     12, 'Changi Facility - Loading Bay Store', 'available',
     '150W daylight 5600K, Bowens mount, DMX capable'),
    ('Chauvet DJ SlimPAR Uplight', 'Lighting',
     'Battery uplighting for evening receptions and banquets.',
     24, 'Changi Facility - Loading Bay Store', 'available',
     'RGB LED, wireless DMX, 10hr battery'),

    -- Staging
    ('Modular Stage Deck 2m x 1m', 'Staging',
     'Interlocking stage platform, height adjustable.',
     20, 'Changi Facility - Loading Bay Store', 'available',
     '2m x 1m, 400mm-800mm adjustable legs, 750kg/sqm load'),
    ('Presentation Lectern', 'Staging',
     'Podium with built-in microphone gooseneck and reading light.',
     5, 'Marina Bay Facility - Store C', 'available',
     'Acrylic front panel, XLR gooseneck input, LED task light'),

    -- Networking
    ('Cisco CBS350 Network Switch', 'Networking',
     'Managed switch for wired event registration desks.',
     6, 'Marina Bay Facility - Server Room', 'available',
     '24-port gigabit, PoE+, managed'),
    ('Ubiquiti UniFi AP U6-Pro', 'Networking',
     'Temporary high-density Wi-Fi for large attendee numbers.',
     10, 'Marina Bay Facility - Server Room', 'available',
     'Wi-Fi 6, 300+ concurrent clients, PoE powered'),

    -- Accessibility
    ('Williams Sound Hearing Loop Kit', 'Accessibility',
     'Portable induction loop for attendees using hearing aids.',
     4, 'Marina Bay Facility - Store C', 'available',
     'Covers 30sqm, T-coil compatible, includes receivers'),
    ('Portable Wheelchair Ramp 1.8m', 'Accessibility',
     'Folding ramp for stage and threshold access.',
     3, 'Changi Facility - Loading Bay Store', 'available',
     '1.8m aluminium, 270kg capacity, non-slip surface'),

    -- Retired, kept for historical reservations
    ('Panasonic PT-VW360 Projector', 'Projection',
     'Legacy projector withdrawn from service; retained for past events.',
     2, 'Jurong Facility - Store B', 'retired',
     'Lamp-based, discontinued, replacement parts unavailable')
) as v(name, category, description, total_quantity, location, operational_status, technical_specs)
where not exists (
    select 1 from public.equipment e where e.name = v.name
);

-- Verify:
select category, operational_status, count(*), sum(total_quantity) as units
from public.equipment
group by category, operational_status
order by category, operational_status;

-- ===== backend/sql/010_seed_venues.sql =====

-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- Seed venues for the "View Venue Details" story. The venues table was
-- empty, and creating venues (VENUE_MANAGE) is a separate story, so there
-- was nothing to view.
--
-- Deliberately varied: one inactive venue, and one with no accessibility
-- features or operating hours recorded, so the "none recorded" states are
-- visible in a demo. Guarded on `name`, as in 006_seed_equipment.sql.

insert into public.venues
    (name, location, capacity, supported_layouts, facilities, accessibility_features,
     operating_hours, is_active)
select v.name, v.location, v.capacity, v.supported_layouts, v.facilities,
       v.accessibility_features, v.operating_hours, v.is_active
from (values
    ('Marina Grand Ballroom', '10 Bayfront Ave, Level 3', 600,
     array['Theatre', 'Banquet', 'Classroom', 'Cocktail'],
     array['Stage', 'Built-in PA system', 'Dual projection screens', 'Green room'],
     array['Wheelchair access', 'Accessible toilets', 'Hearing loop'],
     E'Mon-Fri 08:00-23:00\nSat-Sun 09:00-23:00', true),
    ('Harbourfront Seminar Room 2', '1 Maritime Square, Level 2', 80,
     array['Classroom', 'U-shape', 'Boardroom'],
     array['Projector', 'Whiteboard', 'Video conferencing'],
     array['Wheelchair access', 'Lift access'],
     'Mon-Fri 08:00-18:00', true),
    ('Sentosa Garden Pavilion', '8 Sentosa Gateway', 200,
     array['Banquet', 'Cocktail'],
     array['Outdoor lawn', 'Catering kitchen'],
     array[]::text[],
     null, true),
    ('Changi Business Suite', '2 Changi Business Park Ave 1', 40,
     array['Boardroom'],
     array['Display screen', 'Conference phone'],
     array['Wheelchair access'],
     'Mon-Fri 09:00-17:00', false)
) as v(name, location, capacity, supported_layouts, facilities, accessibility_features,
       operating_hours, is_active)
where not exists (select 1 from public.venues existing where existing.name = v.name);

-- ===== backend/sql/011_seed_venues_for_search.sql =====

-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- More venues for the "Search and Filter Venues" story. 010 seeds four,
-- which is too few to show search and filtering doing anything: a minimum
-- capacity of 100 leaves two results, and there is no way to demonstrate
-- that ticking two facilities requires a venue to have BOTH.
--
-- Built to make each filter visibly bite:
--
--   * keyword  -- "Marina" matches three venues, one of them only through
--                 its location, not its name; "Jurong" matches two.
--   * capacity -- spread from 20 to 1000, so any threshold splits the list.
--   * facilities -- several venues have a Projector, fewer have a Projector
--                 AND Video conferencing, which is what makes "must have
--                 every selected facility" observable.
--   * accessibility -- one venue records none, so filtering on any feature
--                 drops it.
--
-- The layout, facility and accessibility values reuse 010's spelling
-- exactly ('Projector', 'Wheelchair access', 'U-shape', ...). These columns
-- are free text, and the search page builds its filter options from the
-- distinct values recorded, so a new spelling would appear as a separate
-- option rather than matching the existing one.
--
-- Guarded on `name`, as in 006 and 010.

insert into public.venues
    (name, location, capacity, supported_layouts, facilities, accessibility_features,
     operating_hours, is_active)
select v.name, v.location, v.capacity, v.supported_layouts, v.facilities,
       v.accessibility_features, v.operating_hours, v.is_active
from (values
    ('Bayfront Conference Hall A', '10 Bayfront Ave, Marina Bay, Level 4', 300,
     array['Theatre', 'Classroom'],
     array['Projector', 'Built-in PA system', 'Video conferencing', 'Stage'],
     array['Wheelchair access', 'Accessible toilets', 'Hearing loop', 'Lift access'],
     'Mon-Sun 08:00-22:00', true),
    ('Marina Bay Meeting Room 5', '10 Bayfront Ave, Marina Bay, Level 5', 20,
     array['Boardroom'],
     array['Display screen', 'Video conferencing', 'Whiteboard'],
     array['Wheelchair access', 'Lift access'],
     'Mon-Fri 08:00-20:00', true),
    ('Raffles Place Training Studio', '1 Raffles Place, Level 12', 50,
     array['Classroom', 'U-shape'],
     array['Projector', 'Whiteboard'],
     array['Wheelchair access', 'Lift access'],
     'Mon-Fri 08:00-18:00', true),
    ('Jurong Innovation Hub Auditorium', '2 Jurong East Street 21', 250,
     array['Theatre'],
     array['Projector', 'Built-in PA system', 'Stage'],
     array['Wheelchair access', 'Accessible toilets'],
     'Mon-Sat 08:00-22:00', true),
    ('Jurong Innovation Hub Workshop Room', '2 Jurong East Street 21, Level 3', 30,
     array['Classroom', 'U-shape', 'Boardroom'],
     array['Projector', 'Whiteboard', 'Video conferencing'],
     array[]::text[],
     'Mon-Fri 09:00-18:00', true),
    ('Orchard Gallery Loft', '391 Orchard Road, Level 7', 120,
     array['Cocktail', 'Banquet'],
     array['Built-in PA system', 'Catering kitchen'],
     array['Wheelchair access', 'Lift access'],
     E'Tue-Sun 11:00-23:00\nClosed Mondays', true),
    ('Suntec Exhibition Hall 3', '1 Raffles Boulevard, Level 1', 1000,
     array['Theatre', 'Banquet', 'Cocktail'],
     array['Stage', 'Built-in PA system', 'Dual projection screens', 'Green room'],
     array['Wheelchair access', 'Accessible toilets', 'Hearing loop'],
     'Mon-Sun 07:00-23:59', true),
    ('Tanjong Pagar Rooftop Terrace', '7 Wallich Street, Level 30', 150,
     array['Cocktail'],
     array['Catering kitchen', 'Built-in PA system'],
     array['Lift access'],
     'Mon-Sun 17:00-01:00', true)
) as v(name, location, capacity, supported_layouts, facilities, accessibility_features,
       operating_hours, is_active)
where not exists (select 1 from public.venues existing where existing.name = v.name);

-- Verify:
select name, location, capacity, is_active from public.venues order by name;

-- ===== backend/sql/012_seed_venue_availability_demo.sql =====

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

-- ===== backend/sql/018_seed_venue_safety_details.sql =====

-- Run in the Supabase SQL editor, after 017. Safe to re-run (idempotent).
--
-- Seed the emergency access and known restrictions the Safety Officer reads
-- (sql/017) for the venues seeded in 010 and 011. Editing venues
-- (VENUE_MANAGE) is a separate story, so without this every venue would
-- show "None recorded".
--
-- Only fills a value that is still null, so it never overwrites what Venue
-- Staff record later. Sentosa Garden Pavilion is deliberately left out, as
-- in 010, so the "none recorded" state stays visible in a demo.
--
-- Rollback: nothing to undo beyond 017's own rollback (dropping the columns).

update public.venues v
set emergency_access = coalesce(v.emergency_access, s.emergency_access),
    known_restrictions = coalesce(v.known_restrictions, s.known_restrictions)
from (values
    ('Marina Grand Ballroom',
     'Four fire exits (two east, two west) to the Level 3 assembly corridor; fire lift at the service lobby.',
     'No open flames or pyrotechnics. Stage load limit 500 kg/m². Amplified sound must end by 23:00.'),
    ('Harbourfront Seminar Room 2',
     'One fire exit at the rear to stairwell B; main door opens to the Level 2 lift lobby.',
     'Maximum 80 occupants under the fire certificate. No catering equipment with naked flames.'),
    ('Changi Business Suite',
     'Single exit to the main corridor; nearest stairwell 15 m to the left.',
     'Boardroom layout only; furniture is fixed.'),
    ('Bayfront Conference Hall A',
     'Three fire exits to the Level 4 sky bridge and stairwells A and C; muster point at Bayfront Plaza.',
     'Aisles at least 1.2 m wide in theatre layout. No haze or smoke machines (sensitive detectors).'),
    ('Marina Bay Meeting Room 5',
     'One exit to the Level 5 corridor; stairwell C directly opposite.',
     'Maximum 20 occupants. No freestanding equipment in front of the exit.'),
    ('Raffles Place Training Studio',
     'Two exits to the Level 12 lift lobby and the fire stairwell; refuge area beside stairwell.',
     'Building closes to the public at 22:00. Floor-standing equipment must keep 1 m clear of exits.'),
    ('Jurong Innovation Hub Auditorium',
     'Six exits (four at floor level, two at the rear balcony); wheelchair refuge bays at both rear exits.',
     'Fixed tiered seating; no standing audience in aisles. Rigging only from the house grid.'),
    ('Jurong Innovation Hub Workshop Room',
     'Two exits to the Level 3 corridor; emergency shower at the north wall.',
     'Power tools need a hub technician present. Maximum 30 occupants.'),
    ('Orchard Gallery Loft',
     'Main stair and one fire escape to the Level 7 rear service corridor.',
     'Artworks on display: no food or drink within 1 m of the walls, no wall fixings.'),
    ('Suntec Exhibition Hall 3',
     'Eight exits along the north and south walls to Raffles Boulevard; vehicle access via loading bay 3.',
     'Booth construction must keep 3 m fire lanes clear. Vehicles in the hall only with the venue''s permit.'),
    ('Tanjong Pagar Rooftop Terrace',
     'Two stairwells to Level 29; lifts are not to be used in an emergency.',
     'Outdoor: events are halted in lightning warnings. No open flames; maximum 150 occupants.')
) as s(name, emergency_access, known_restrictions)
where v.name = s.name
  and (v.emergency_access is null or v.known_restrictions is null);

-- ===== backend/sql/026_seed_venue_setup_turnaround_demo.sql =====

-- Run in the Supabase SQL editor, after 021. Safe to re-run (idempotent).
--
-- Demo values for "Filter Venues by Date and Time". A venue's setup and
-- turnaround start unset (sql/021_venue_setup_turnaround.sql, read as 0),
-- which changes nothing; these give three seeded venues realistic values so
-- the effect can be seen. Venue Staff can change them on the venue's page.
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

