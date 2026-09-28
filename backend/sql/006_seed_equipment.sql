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
