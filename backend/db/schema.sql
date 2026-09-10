-- ConnectSphere core schema, v1
-- Run once against a fresh Supabase Postgres database.
-- Matches the ER diagram reviewed 2026-09-10.

-- ===== Enums =====

create type user_role as enum (
    'organiser', 'coordinator', 'venue_staff', 'tech_support', 'attendee'
);

create type event_status as enum (
    'draft', 'submitted', 'under_review', 'changes_requested',
    'approved', 'rejected', 'planning', 'confirmed', 'completed', 'cancelled'
);

create type booking_status as enum (
    'pending', 'approved', 'rejected', 'cancelled'
);

create type equipment_status as enum (
    'requested', 'reviewing', 'reserved', 'rejected', 'cancelled'
);

create type registration_status as enum (
    'registered', 'withdrawn'
);

create type change_request_status as enum (
    'pending', 'approved', 'rejected'
);

-- ===== Identity =====

create table users (
    id bigint generated always as identity primary key,
    name text not null,
    email text not null unique,
    password_hash text not null,
    role user_role not null,
    created_at timestamptz not null default now()
);

-- ===== Event lifecycle =====

create table events (
    id bigint generated always as identity primary key,
    organiser_id bigint not null references users (id) on delete restrict,
    coordinator_id bigint references users (id) on delete set null,
    name text not null,
    purpose text,
    description text,
    proposed_start timestamptz not null,
    proposed_end timestamptz not null,
    expected_attendance integer not null check (expected_attendance > 0),
    venue_requirements text,
    accessibility_needs text,
    equipment_requirements text,
    registration_enabled boolean not null default false,
    status event_status not null default 'draft',
    submitted_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (proposed_end > proposed_start)
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
    created_at timestamptz not null default now(),
    reviewed_at timestamptz,
    check (end_time > start_time)
);

create index idx_venue_bookings_event on venue_bookings (event_id);
create index idx_venue_bookings_venue_time on venue_bookings (venue_id, start_time, end_time);

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
    category text,
    total_quantity integer not null check (total_quantity >= 0),
    technical_specs text
);

create table equipment_requests (
    id bigint generated always as identity primary key,
    event_id bigint not null references events (id) on delete cascade,
    equipment_id bigint not null references equipment (id) on delete restrict,
    reviewed_by bigint references users (id) on delete set null,
    quantity_requested integer not null check (quantity_requested > 0),
    technical_requirements text,
    status equipment_status not null default 'requested',
    notes text,
    created_at timestamptz not null default now(),
    reviewed_at timestamptz
);

create index idx_equipment_requests_event on equipment_requests (event_id);
create index idx_equipment_requests_equipment on equipment_requests (equipment_id);

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
