-- ConnectSphere core schema, v1
-- Run once against a fresh Supabase Postgres database.
-- Matches the ER diagram reviewed 2026-09-10.

-- ===== Enums =====

create type user_role as enum (
    'organiser', 'coordinator', 'venue_staff', 'tech_support', 'attendee',
    'event_coordinator_lead', 'safety_officer'
);

-- The Event statuses of dod.md section 11a, and no others.
create type event_status as enum (
    'draft', 'submitted_awaiting_coordinator', 'under_review',
    'awaiting_organiser_reply', 'event_approved', 'planning_event',
    'awaiting_safety_check', 'safety_check_passed', 'event_completed',
    'event_rejected', 'event_cancelled'
);

create type booking_status as enum (
    'pending', 'approved', 'rejected', 'cancelled'
);

-- Lifecycle of an equipment REQUEST (on equipment_requests).
create type equipment_status as enum (
    'requested', 'reviewing', 'reserved', 'rejected', 'cancelled'
);

-- Condition of a physical equipment ITEM (on equipment). Deliberately
-- separate from equipment_status above: "this request is reserved" and
-- "this projector works" are different facts about different things.
create type equipment_operational_status as enum (
    'available', 'maintenance', 'damaged', 'retired'
);

create type registration_status as enum (
    'registered', 'withdrawn'
);

create type change_request_status as enum (
    'pending', 'approved', 'rejected'
);

create type communication_preference as enum (
    'email', 'sms', 'phone_call'
);

-- ===== Identity =====

create table users (
    id bigint generated always as identity primary key,
    name text not null,
    email text not null unique,
    password_hash text not null,
    role user_role not null,
    -- Toggled by an Event Coordinator to say "don't route events to me
    -- right now" -- see sql/004_coordinator_availability.sql. Every role
    -- gets the column since users is one shared table; only Coordinators
    -- ever read or write it.
    is_available boolean not null default true,
    created_at timestamptz not null default now(),
    -- Added for the "Edit User Profile" story; all nullable since every
    -- user is expected to fill these in after account creation, not at
    -- registration time. See sql/009_user_profile_fields.sql.
    organisation text,
    phone_country_code text,
    phone_number text,
    communication_preference communication_preference
);

-- One row per real change of a Coordinator's is_available flag -- see
-- sql/008_coordinator_availability_history.sql. Logged even when the
-- Coordinator has zero active events, unlike event_status_history below
-- (which needs an event_id and only records a toggle indirectly, as a
-- side effect of reassigning an event).
create table coordinator_availability_history (
    id bigint generated always as identity primary key,
    coordinator_id bigint not null references users (id) on delete cascade,
    is_available boolean not null,
    created_at timestamptz not null default now()
);

create index idx_coordinator_availability_history_coordinator
    on coordinator_availability_history (coordinator_id, created_at desc);

-- ===== Event lifecycle =====

create table events (
    id bigint generated always as identity primary key,
    organiser_id bigint not null references users (id) on delete restrict,
    coordinator_id bigint references users (id) on delete set null,
    -- name / proposed_* / expected_attendance are nullable so an
    -- INCOMPLETE request can be stored as a draft. Completeness is
    -- enforced at submit time by the API, which reports which mandatory
    -- fields are missing. See sql/003_events_draft_fields.sql.
    name text,
    purpose text,
    event_type text,
    description text,
    programme text,
    proposed_start timestamptz,
    proposed_end timestamptz,
    expected_attendance integer check (expected_attendance > 0),
    venue_requirements text,
    room_layout_preference text,
    accessibility_needs text,
    equipment_requirements text,
    special_arrangements text,
    registration_enabled boolean not null default false,
    registration_opens_at timestamptz,
    registration_closes_at timestamptz,
    status event_status not null default 'draft',
    submitted_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (proposed_end > proposed_start),
    check (registration_closes_at >= registration_opens_at)
);

create index idx_events_organiser on events (organiser_id);
create index idx_events_coordinator on events (coordinator_id);
create index idx_events_status on events (status);

create table event_status_history (
    id bigint generated always as identity primary key,
    event_id bigint not null references events (id) on delete cascade,
    changed_by bigint not null references users (id) on delete restrict,
    from_status text,
    to_status text not null,
    note text,
    created_at timestamptz not null default now()
);

create index idx_event_status_history_event on event_status_history (event_id);

create table event_change_requests (
    id bigint generated always as identity primary key,
    event_id bigint not null references events (id) on delete cascade,
    requested_by bigint not null references users (id) on delete restrict,
    reviewed_by bigint references users (id) on delete set null,
    description text not null,
    proposed_changes jsonb,
    status change_request_status not null default 'pending',
    review_notes text,
    created_at timestamptz not null default now(),
    reviewed_at timestamptz
);

create index idx_event_change_requests_event on event_change_requests (event_id);

-- ===== Venue =====

create table venues (
    id bigint generated always as identity primary key,
    name text not null,
    location text not null,
    capacity integer not null check (capacity > 0),
    facilities text[] not null default '{}',
    accessibility_features text[] not null default '{}',
    supported_layouts text[] not null default '{}',
    operating_hours text,
    -- Read by the Safety Officer; see sql/017_safety_check.sql.
    emergency_access text,
    known_restrictions text,
    is_active boolean not null default true
);

create index idx_venues_facilities on venues using gin (facilities);
create index idx_venues_accessibility on venues using gin (accessibility_features);

create table venue_bookings (
    id bigint generated always as identity primary key,
    event_id bigint not null references events (id) on delete cascade,
    venue_id bigint not null references venues (id) on delete restrict,
    requested_by bigint not null references users (id) on delete restrict,
    reviewed_by bigint references users (id) on delete set null,
    start_time timestamptz not null,
    end_time timestamptz not null,
    status booking_status not null default 'pending',
    decision_notes text,
    -- What Venue Staff offer instead when rejecting; see sql/014.
    suggested_alternative text,
    -- Set by a Safety Officer to send the booking back for review without
    -- releasing it; see sql/017_safety_check.sql.
    safety_recheck_reason text,
    created_at timestamptz not null default now(),
    reviewed_at timestamptz,
    check (end_time > start_time)
);

create index idx_venue_bookings_event on venue_bookings (event_id);
create index idx_venue_bookings_venue_time on venue_bookings (venue_id, start_time, end_time);

-- One live (pending or approved) request per event; see sql/013.
create unique index uq_venue_bookings_one_live_per_event
    on venue_bookings (event_id) where status in ('pending', 'approved');

create table venue_unavailability (
    id bigint generated always as identity primary key,
    venue_id bigint not null references venues (id) on delete cascade,
    start_time timestamptz not null,
    end_time timestamptz not null,
    reason text,
    created_by bigint not null references users (id) on delete restrict,
    check (end_time > start_time)
);

create index idx_venue_unavailability_venue_time on venue_unavailability (venue_id, start_time, end_time);

-- ===== Equipment =====

create table equipment (
    id bigint generated always as identity primary key,
    name text not null,
    -- The equipment "type" the catalogue is filtered by.
    category text,
    -- Plain-language description of what the item is. Distinct from
    -- technical_specs, which holds model numbers, wattage and connectors.
    description text,
    total_quantity integer not null check (total_quantity >= 0),
    -- Where the item is physically stored; equipment held at another
    -- venue may not be usable for a given event.
    location text,
    operational_status equipment_operational_status not null default 'available',
    technical_specs text
);

create index idx_equipment_category on equipment (category);

create table equipment_requests (
    id bigint generated always as identity primary key,
    event_id bigint not null references events (id) on delete cascade,
    equipment_id bigint not null references equipment (id) on delete restrict,
    reviewed_by bigint references users (id) on delete set null,
    quantity_requested integer not null check (quantity_requested > 0),
    technical_requirements text,
    status equipment_status not null default 'requested',
    notes text,
    -- Where the item is set up, and a Safety Officer's re-review flag; see
    -- sql/017_safety_check.sql.
    placement_notes text,
    safety_recheck_reason text,
    created_at timestamptz not null default now(),
    reviewed_at timestamptz,
    -- One line per equipment item, per event. Quantity is how you ask for
    -- more of something, so two lines naming the same item is always a
    -- mistake -- and would have to be summed everywhere availability is
    -- calculated. The API rejects duplicates with a 422; this is the
    -- backstop for anything that writes without going through it.
    constraint equipment_requests_event_equipment_key unique (event_id, equipment_id)
);

create index idx_equipment_requests_event on equipment_requests (event_id);
create index idx_equipment_requests_equipment on equipment_requests (equipment_id);

-- The Coordinator's own record of what an event needs: a catalogue category,
-- a quantity and technical notes. Separate from equipment_requests, which
-- holds the ORGANISER's picks -- an approved Organiser change request deletes
-- and rebuilds every one of those for the event, and a requirement stored
-- there would go with them.
--
-- organiser_equipment_request_id links FROM a requirement TO the pick it was
-- based on (the Organiser's table knows nothing about requirements). Nullable
-- because a requirement may not come from a pick; SET NULL because replacing
-- the pick must never delete the requirement.
create table coordinator_equipment_requirements (
    id bigint generated always as identity primary key,
    event_id bigint not null references events (id) on delete cascade,
    organiser_equipment_request_id bigint references equipment_requests (id) on delete set null,
    category text not null check (length(btrim(category)) > 0),
    quantity_needed integer not null check (quantity_needed > 0),
    technical_notes text,
    status equipment_status not null default 'requested',
    created_by bigint not null references users (id) on delete restrict,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index idx_coordinator_equipment_requirements_event
    on coordinator_equipment_requirements (event_id);
create index idx_coordinator_equipment_requirements_pick
    on coordinator_equipment_requirements (organiser_equipment_request_id)
    where organiser_equipment_request_id is not null;

-- Which reserved item is fulfilling which requirement. The reservation itself
-- is the existing one (an equipment_requests row moved to 'reserved'); this
-- adds nothing to it. Keyed by (event, item) rather than the row's id so the
-- link is written in the same commit as the reservation, and survives an
-- approved Organiser change that rebuilds those rows. How much a requirement
-- has reserved is read from the reserved rows, never stored here.
create table coordinator_requirement_reservations (
    id bigint generated always as identity primary key,
    requirement_id bigint not null
        references coordinator_equipment_requirements (id) on delete cascade,
    event_id bigint not null references events (id) on delete cascade,
    equipment_id bigint not null references equipment (id) on delete restrict,
    created_at timestamptz not null default now(),
    constraint coordinator_requirement_reservations_event_item_key
        unique (event_id, equipment_id)
);

create index idx_coordinator_requirement_reservations_requirement
    on coordinator_requirement_reservations (requirement_id);

-- ===== Attendance & comms =====

create table registrations (
    id bigint generated always as identity primary key,
    event_id bigint not null references events (id) on delete cascade,
    attendee_id bigint not null references users (id) on delete restrict,
    status registration_status not null default 'registered',
    registered_at timestamptz not null default now(),
    withdrawn_at timestamptz,
    unique (event_id, attendee_id)
);

create table notifications (
    id bigint generated always as identity primary key,
    user_id bigint not null references users (id) on delete cascade,
    event_id bigint references events (id) on delete cascade,
    type text not null,
    message text not null,
    is_read boolean not null default false,
    created_at timestamptz not null default now()
);

create index idx_notifications_user_unread on notifications (user_id, is_read);
