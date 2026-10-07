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
