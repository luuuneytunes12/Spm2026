-- Run in the Supabase SQL editor. Safe to re-run (idempotent).
--
-- A tentative hold whose expiry passes now becomes 'hold_expired' (it used to
-- become 'cancelled'), and the Coordinator is reminded once before expiry;
-- hold_reminder_sent_at records when. Holds that expired before this
-- migration stay 'cancelled' with the note "Tentative hold expired.".
-- Needs sql/026_venue_hold_required_action.sql applied first.
-- Rollback: sql/down/027_venue_hold_expired_status.sql

alter type public.booking_status add value if not exists 'hold_expired';

alter table public.venue_bookings add column if not exists hold_reminder_sent_at timestamptz;
