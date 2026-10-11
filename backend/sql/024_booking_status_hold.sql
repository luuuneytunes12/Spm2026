-- A tentative hold is a venue booking status (SCRUM-97 places holds;
-- SCRUM-92 re-checks active holds when a venue's setup/turnaround changes).
-- Nothing is rewritten: no existing row has this status.
-- Undo with sql/down/024_booking_status_hold.sql.

alter type booking_status add value if not exists 'hold';
