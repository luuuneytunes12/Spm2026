alter table public.users drop column if exists responsibilities;
alter table public.users drop column if exists department;
drop type if exists department;
