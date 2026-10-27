# backend/sql (frozen)

The hand-run migrations from before the deploy pipeline existed, kept as
history because comments across the codebase cite them by number. 001-028
are folded into `supabase/migrations/20261016000000_baseline.sql`, 029-033
are copied into `supabase/migrations/` one for one, and the seed files are in
`supabase/seed.sql`.

**Do not add new files here.** For a schema change:

1. `npx supabase migration new <name>`, and write the SQL in the file it creates
   under `supabase/migrations/`.
2. Make the same change to `backend/db/schema.sql`, which the tests and the
   e2e suite build their databases from.

Merging to `main` applies the migration to staging; pushing a `v*` tag
applies it to production. See `.github/workflows/deploy.yml`.
