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
