-- Undo sql/018_event_statuses_follow_dod.sql.
--
-- An event sitting in 'awaiting_safety_check' (a status the old schema does
-- not have) goes back to 'planning', the stage before it. Postgres cannot
-- drop an enum value, so the type is rebuilt.

update event_status_history set
    from_status = case from_status
        when 'submitted_awaiting_coordinator' then 'submitted'
        when 'awaiting_organiser_reply' then 'changes_requested'
        when 'event_approved' then 'approved'
        when 'planning_event' then 'planning'
        when 'awaiting_safety_check' then 'planning'
        when 'safety_check_passed' then 'confirmed'
        when 'event_completed' then 'completed'
        when 'event_rejected' then 'rejected'
        when 'event_cancelled' then 'cancelled'
        else from_status end,
    to_status = case to_status
        when 'submitted_awaiting_coordinator' then 'submitted'
        when 'awaiting_organiser_reply' then 'changes_requested'
        when 'event_approved' then 'approved'
        when 'planning_event' then 'planning'
        when 'awaiting_safety_check' then 'planning'
        when 'safety_check_passed' then 'confirmed'
        when 'event_completed' then 'completed'
        when 'event_rejected' then 'rejected'
        when 'event_cancelled' then 'cancelled'
        else to_status end;

alter type event_status rename to event_status_new;
create type event_status as enum (
    'draft', 'submitted', 'under_review', 'changes_requested',
    'approved', 'rejected', 'planning', 'confirmed', 'completed', 'cancelled'
);
alter table events alter column status drop default;
alter table events alter column status type event_status using (
    case status::text
        when 'submitted_awaiting_coordinator' then 'submitted'
        when 'awaiting_organiser_reply' then 'changes_requested'
        when 'event_approved' then 'approved'
        when 'planning_event' then 'planning'
        when 'awaiting_safety_check' then 'planning'
        when 'safety_check_passed' then 'confirmed'
        when 'event_completed' then 'completed'
        when 'event_rejected' then 'rejected'
        when 'event_cancelled' then 'cancelled'
        else status::text end
)::event_status;
alter table events alter column status set default 'draft';
drop type event_status_new;
