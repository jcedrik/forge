"""Turn the Secrets Manager JSON that ECS injects as DB_CREDENTIALS into a
DATABASE_URL, so db.py stays ignorant of where credentials come from.

Used by the task definition through `python -m app.entrypoint_env` if you
prefer that over computing the URL in the container command. Kept tiny.
"""

import json
import os


def database_url() -> str:
    raw = os.environ.get("DB_CREDENTIALS")
    host = os.environ.get("DB_HOST")
    if not raw or not host:
        return os.environ.get("DATABASE_URL", "sqlite:////tmp/forge.db")
    creds = json.loads(raw)
    return f"postgresql://{creds['username']}:{creds['password']}@{host}:5432/forge?sslmode=require"


if __name__ == "__main__":
    print(database_url())
