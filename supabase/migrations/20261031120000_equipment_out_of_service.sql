-- SCRUM-115 Mark Equipment Damaged or Under Maintenance. Safe to re-run
-- (idempotent). backend/db/schema.sql carries the same change.
-- Rollback: supabase/rollbacks/20261031120000_equipment_out_of_service.down.sql

-- Units out of service, whatever the window. operational_status is about the
-- whole item; these are about part of it.
alter table public.equipment
    add column if not exists damaged_quantity integer not null default 0,
    add column if not exists maintenance_quantity integer not null default 0;

alter table public.equipment
    drop constraint if exists ck_equipment_damaged_quantity,
    drop constraint if exists ck_equipment_maintenance_quantity,
    drop constraint if exists ck_equipment_out_of_service_within_total;
alter table public.equipment
    add constraint ck_equipment_damaged_quantity check (damaged_quantity >= 0),
    add constraint ck_equipment_maintenance_quantity check (maintenance_quantity >= 0),
    add constraint ck_equipment_out_of_service_within_total
        check (damaged_quantity + maintenance_quantity <= total_quantity);

-- Append-only: who marked or returned how many units, and when.
create table if not exists public.equipment_activity (
    id bigint generated always as identity primary key,
    equipment_id bigint not null references public.equipment (id) on delete cascade,
    changed_by bigint references public.users (id) on delete set null,
    note text not null,
    created_at timestamptz not null default now()
);
create index if not exists idx_equipment_activity_equipment
    on public.equipment_activity (equipment_id, created_at desc);

create or replace function public.refuse_equipment_activity_mutation()
returns trigger
language plpgsql
as $$
begin
    -- An entry may go only with its item (ON DELETE CASCADE), or lose its
    -- actor when that user is deleted (ON DELETE SET NULL).
    if tg_op = 'DELETE'
       and not exists (select 1 from public.equipment where id = old.equipment_id) then
        return old;
    end if;
    if tg_op = 'UPDATE' and new.changed_by is null
       and new.equipment_id = old.equipment_id and new.note = old.note
       and new.created_at = old.created_at then
        return new;
    end if;
    raise exception 'Equipment activity log entries are immutable';
end;
$$;

drop trigger if exists equipment_activity_immutable on public.equipment_activity;
create trigger equipment_activity_immutable
    before update or delete on public.equipment_activity
    for each row execute function public.refuse_equipment_activity_mutation();
