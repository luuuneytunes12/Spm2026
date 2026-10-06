-- Event statuses follow dod.md section 11a exactly.
--
--   submitted         -> submitted_awaiting_coordinator
--   changes_requested -> awaiting_organiser_reply
--   approved          -> event_approved
--   planning          -> planning_event
--   confirmed         -> safety_check_passed   ("Safety Check Passed (Event Confirmed)")
--   completed         -> event_completed
--   rejected          -> event_rejected
--   cancelled         -> event_cancelled
--   (new)                awaiting_safety_check
--   draft, under_review are unchanged.
--
-- event_status_history keeps statuses as plain text, so its old rows are
-- rewritten too: the log must read the same as the live status.
-- Undo with sql/down/018_event_statuses_follow_dod.sql.

alter type event_status rename value 'submitted' to 'submitted_awaiting_coordinator';
alter type event_status rename value 'changes_requested' to 'awaiting_organiser_reply';
alter type event_status rename value 'approved' to 'event_approved';
alter type event_status rename value 'planning' to 'planning_event';
alter type event_status rename value 'confirmed' to 'safety_check_passed';
alter type event_status rename value 'completed' to 'event_completed';
alter type event_status rename value 'rejected' to 'event_rejected';
alter type event_status rename value 'cancelled' to 'event_cancelled';
alter type event_status add value if not exists 'awaiting_safety_check' after 'planning_event';

update event_status_history set
    from_status = case from_status
        when 'submitted' then 'submitted_awaiting_coordinator'
        when 'changes_requested' then 'awaiting_organiser_reply'
        when 'approved' then 'event_approved'
        when 'planning' then 'planning_event'
        when 'confirmed' then 'safety_check_passed'
        when 'completed' then 'event_completed'
        when 'rejected' then 'event_rejected'
        when 'cancelled' then 'event_cancelled'
        else from_status end,
    to_status = case to_status
        when 'submitted' then 'submitted_awaiting_coordinator'
        when 'changes_requested' then 'awaiting_organiser_reply'
        when 'approved' then 'event_approved'
        when 'planning' then 'planning_event'
        when 'confirmed' then 'safety_check_passed'
        when 'completed' then 'event_completed'
        when 'rejected' then 'event_rejected'
        when 'cancelled' then 'event_cancelled'
        else to_status end;
