from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchored to backend/.env rather than a bare ".env", which pydantic-settings
# would resolve against the current working directory -- that breaks any entry
# point invoked from somewhere other than backend/ (e.g. scripts/).
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    # Supabase Postgres connection string, e.g.
    # postgresql+psycopg://postgres:[PASSWORD]@[HOST]:5432/postgres
    database_url: str

    # Optional, unused by the current direct-Postgres setup. Only needed
    # if you later add supabase-py for auth/storage/realtime, or verify
    # Supabase Auth JWTs server-side.
    supabase_url: str | None = None
    supabase_publishable_key: str | None = None
    supabase_secret_key: str | None = None
    supabase_jwks_url: str | None = None

    # Comma-separated list of allowed origins for CORS.
    cors_origins: str = "http://localhost:5173"

    # JWT auth settings (backend-issued tokens; see app/core/security.py).
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 30
    refresh_token_ttl_days: int = 7

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
