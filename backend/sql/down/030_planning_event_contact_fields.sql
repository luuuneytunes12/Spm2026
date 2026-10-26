ALTER TABLE public.events
    DROP COLUMN IF EXISTS event_contact_email,
    DROP COLUMN IF EXISTS event_contact_name;
