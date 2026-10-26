-- Run in the Supabase SQL editor. Safe to re-run.
-- Rollback: sql/down/030_planning_event_contact_fields.sql
-- These are the event's contact details, independent of its Organiser account.
ALTER TABLE public.events
    ADD COLUMN IF NOT EXISTS event_contact_name text,
    ADD COLUMN IF NOT EXISTS event_contact_email text;
