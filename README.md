# Spm2026

Full-stack app: React (Vite) frontend + FastAPI backend + Supabase Postgres.

```
Spm2026/
├── frontend/   # React + Vite + TypeScript
└── backend/    # FastAPI + SQLAlchemy
```

The frontend never talks to Supabase directly — it calls the FastAPI
backend over HTTP, and the backend is the only thing holding the
database credentials. Keep it that way unless you have a specific
reason to add client-side Supabase access (e.g. `supabase-js` for
Supabase Auth or Realtime).

## Prerequisites

- Node.js 20+ and npm
- Python 3.11+ and [uv](https://docs.astral.sh/uv/getting-started/installation/)
- A Supabase project (free tier is fine) — [supabase.com](https://supabase.com/dashboard)

## 1. Get your Supabase connection details

1. In the Supabase dashboard: **Project Settings → Database → Connection string → URI**.
2. Copy it. For local dev / a normal long-lived server, the direct
   connection URI is fine. If you'll deploy the backend somewhere
   serverless (Lambda, Vercel functions, etc.), use the **Session
   pooler** or **Transaction pooler** URI instead — the direct
   connection doesn't handle many short-lived connections well.
3. You'll also find your project URL and API keys under
   **Project Settings → API**, only needed if you later use
   `supabase-py`/`supabase-js` for auth/storage/realtime instead of
   raw Postgres.

## 2. Backend setup

```bash
cd backend
uv sync                # creates .venv and installs deps from uv.lock

cp .env.example .env
# edit .env and paste in your Supabase DATABASE_URL
```

`backend/.env`:
```
DATABASE_URL=postgresql+psycopg://postgres:[YOUR-PASSWORD]@[PROJECT-REF].supabase.co:5432/postgres
CORS_ORIGINS=http://localhost:5173
```

Run the API:
```bash
uv run uvicorn app.main:app --reload
```

Check it's up and can reach the database:
```bash
curl http://localhost:8000/health       # {"status": "ok"}
curl http://localhost:8000/health/db    # {"status": "ok", "database": "connected"}
```

Interactive API docs: http://localhost:8000/docs

### Backend layout
```
backend/
├── app/
│   ├── main.py           # FastAPI app, CORS, router registration
│   ├── core/
│   │   ├── config.py     # env-driven settings (pydantic-settings)
│   │   └── db.py         # SQLAlchemy engine/session
│   ├── models/           # SQLAlchemy models (example.py is a stub)
│   └── routers/          # API route modules (health.py is a stub)
├── pyproject.toml
├── uv.lock                # commit this — pins exact resolved versions
└── .env.example
```
Add a new dependency with `uv add <package>` (or `uv add --dev <package>`
for dev-only tools like pytest/ruff) rather than editing
`pyproject.toml` by hand — it keeps `uv.lock` in sync.
Add new endpoints as router modules under `app/routers/` and include
them in `app/main.py`. If you're managing your schema through
Supabase migrations/SQL editor rather than SQLAlchemy, you can ignore
`app/models/` or use it just for typed read access.

## 3. Frontend setup

```bash
cd frontend
npm install
cp .env.example .env
```

`frontend/.env`:
```
VITE_API_URL=http://localhost:8000
```

Run the dev server:
```bash
npm run dev
```

Open http://localhost:5173 — the page includes a small "Backend API"
status line that calls the FastAPI `/health` endpoint, so you can
confirm frontend → backend → Supabase are all wired up correctly.

### Frontend layout
```
frontend/
├── src/
│   ├── lib/api.ts   # fetch wrapper, reads VITE_API_URL
│   ├── App.tsx
│   └── main.tsx
├── .env.example
└── vite.config.ts
```
Call the backend from anywhere in the app with `apiFetch('/your-route')`
from `src/lib/api.ts`.

## Running both together

Two terminals:
```bash
# terminal 1
cd backend && uv run uvicorn app.main:app --reload

# terminal 2
cd frontend && npm run dev
```

## Environment variables & secrets

- Every real `.env` file is gitignored (root, `frontend/`, and
  `backend/` each have their own `.gitignore`) — only the checked-in
  `.env.example` templates should ever be committed.
- `DATABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are backend-only
  secrets. Never expose them to the frontend or prefix them with
  `VITE_` — anything with that prefix gets bundled into the
  client-side JS and is publicly visible.
- If you later add Supabase client-side (e.g. for Supabase Auth),
  only the `anon` public key goes in the frontend, as
  `VITE_SUPABASE_ANON_KEY` — never the `service_role` key.

## Deployment notes

- Backend: any host that runs a Python ASGI app (Fly.io, Render,
  Railway, an EC2 box, etc.). Set `DATABASE_URL` and `CORS_ORIGINS`
  (your production frontend origin) as environment variables there —
  don't ship a `.env` file.
- Frontend: any static host (Vercel, Netlify, Cloudflare Pages,
  `npm run build` → serve `dist/`). Set `VITE_API_URL` to your
  deployed backend's URL as a build-time environment variable.
