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
