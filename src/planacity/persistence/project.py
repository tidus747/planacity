"""Local SQLite projects and atomic JSON backups; never partially overwrite a file."""

import os
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from planacity.domain import ProgramPlan
from planacity.persistence.codec import SCHEMA_VERSION, dumps, loads

APPLICATION_ID = 0x504C414E


@contextmanager
def _replacement(path: Path) -> Iterator[Path]:
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        yield temporary
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_project(path: Path) -> ProgramPlan:
    """Read without creating a missing file or changing a foreign SQLite database."""
    try:
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            if connection.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID:
                raise ValueError("This file is not a Planacity project.")
            project_version = connection.execute("PRAGMA user_version").fetchone()[0]
            if project_version not in (1, SCHEMA_VERSION):
                raise ValueError("Unsupported project version. Use a compatible Planacity version.")
            tables = connection.execute(
                "SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            ).fetchall()
            if tables != [("table", "document")]:
                raise ValueError("Unexpected project schema; refusing to ignore additional data.")
            columns = connection.execute("PRAGMA table_info(document)").fetchall()
            if [column[1] for column in columns] != ["id", "payload"]:
                raise ValueError("Unexpected project columns.")
            rows = connection.execute("SELECT id, payload FROM document").fetchall()
            if len(rows) != 1 or rows[0][0] != 1 or not isinstance(rows[0][1], str):
                raise ValueError("The project must contain exactly one complete plan.")
            return loads(rows[0][1], expected_schema_version=project_version)
        finally:
            connection.close()
    except (sqlite3.Error, ValueError) as error:
        raise ValueError(f"Cannot open '{path}': {error}") from error


def save_project(plan: ProgramPlan, path: Path) -> None:
    payload = dumps(plan)
    if path.exists():
        load_project(path)  # Never overwrite foreign, corrupt, or newer-format data.
    with _replacement(path) as temporary:
        connection = sqlite3.connect(temporary)
        try:
            with connection:
                connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
                connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                connection.execute(
                    "CREATE TABLE document "
                    "(id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)"
                )
                connection.execute("INSERT INTO document VALUES (1, ?)", (payload,))
        finally:
            connection.close()


def export_backup(plan: ProgramPlan, path: Path) -> None:
    export_text(dumps(plan), path)


def export_text(payload: str, path: Path) -> None:
    """Atomically replace a user-selected text export after UI overwrite confirmation."""
    with _replacement(path) as temporary:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())


def restore_backup(path: Path) -> ProgramPlan:
    try:
        return loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as error:
        raise ValueError(f"Cannot restore '{path}': {error}") from error
