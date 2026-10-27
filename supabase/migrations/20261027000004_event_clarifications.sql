-- From backend/sql/032_event_clarifications.sql. Safe to re-run: staging had part of this
-- applied by hand before the pipeline existed.

-- SCRUM-27 / SCRUM-103: the clarification exchange on an Event.
-- notifications.type is plain text, so the two new types
-- (clarification_requested, clarification_replied) need no DDL.
-- Safe to re-run.

create table if not exists event_clarifications (
    id bigint generated always as identity primary key,
    event_id bigint not null references events (id) on delete cascade,
    kind text not null check (kind in ('request', 'reply')),
    message text not null,
    author_id bigint not null references users (id) on delete restrict,
    created_at timestamptz not null default now()
);

create index if not exists idx_event_clarifications_event on event_clarifications (event_id);
