"""Safely rebuild the local SQLite demo database, keeping a timestamped backup.

This is intentionally restricted to APP_ENV=development and a SQLite database
inside the backend directory. Private uploaded evidence is never touched.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.config import get_settings


def reset_demo_database() -> Path | None:
    settings = get_settings()
    if settings.app_env.lower() != "development":
        raise RuntimeError("Demo reset is allowed only when APP_ENV=development.")

    url = make_url(settings.database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise RuntimeError("Demo reset supports only a file-backed SQLite database.")

    db_path = Path(url.database)
    if not db_path.is_absolute():
        db_path = (Path.cwd() / db_path).resolve()
    backend_dir = Path(__file__).resolve().parents[1]
    if not db_path.is_relative_to(backend_dir):
        raise RuntimeError(f"Refusing to reset a database outside {backend_dir}.")

    backup_path: Path | None = None
    if db_path.exists():
        backup_path = db_path.with_name(
            f"{db_path.name}.backup-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        )
        suffix = 1
        while backup_path.exists():
            backup_path = db_path.with_name(
                f"{db_path.name}.backup-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{suffix}"
            )
            suffix += 1
        # SQLite's backup API includes committed WAL contents; a plain file copy
        # can miss transactions that have not checkpointed yet.
        with sqlite3.connect(db_path) as source, sqlite3.connect(backup_path) as backup:
            source.backup(backup)
        print(f"Backed up existing local database to: {backup_path}")

    for sidecar in (Path(f"{db_path}-wal"), Path(f"{db_path}-shm")):
        if sidecar.exists():
            sidecar.unlink()
    if db_path.exists():
        db_path.unlink()

    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=backend_dir, check=True)
    subprocess.run([sys.executable, "-m", "scripts.seed_demo"], cwd=backend_dir, check=True)
    return backup_path


def main() -> None:
    backup = reset_demo_database()
    print("Local SQLite demo database rebuilt with synthetic demo records.")
    if backup is not None:
        print("Previous database is preserved in the backup file shown above.")
    print("Private uploaded documents were not changed. Re-run scripts.seed_users to recreate login accounts.")


if __name__ == "__main__":
    main()
