-- Undoes supabase/migrations/20261031120000_equipment_out_of_service.sql.
-- Run by hand: this folder is not applied by the deploy pipeline. Loses which
-- units are out of service, and their log.

drop table if exists public.equipment_activity;
drop function if exists public.refuse_equipment_activity_mutation();

alter table public.equipment
    drop constraint if exists ck_equipment_out_of_service_within_total,
    drop constraint if exists ck_equipment_maintenance_quantity,
    drop constraint if exists ck_equipment_damaged_quantity,
    drop column if exists maintenance_quantity,
    drop column if exists damaged_quantity;
