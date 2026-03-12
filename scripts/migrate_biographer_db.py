#!/usr/bin/env python3
"""
Migrate Biographer SQLite database → Remi SQLite database.

Copies all data (conversations, messages, entities, facts, relationships,
provenance, coverage, agent_state) from the old Biographer DB into Remi's DB.

Both apps share the same schema, so this is a direct table copy with
duplicate handling (existing records in Remi are kept; Biographer data
fills in anything missing).

Usage:
    python scripts/migrate_biographer_db.py
    python scripts/migrate_biographer_db.py \
        --src "/Users/timothyjordan/Programming Projects/Biographer/backend/data/biographer.db" \
        --dst ~/Git/Remi/backend/data/remi.db
"""

import argparse
import asyncio
import sqlite3
import sys
from pathlib import Path

DEFAULT_SRC = Path.home() / "Programming Projects" / "Biographer" / "backend" / "data" / "biographer.db"
DEFAULT_DST = Path(__file__).parent.parent / "backend" / "data" / "remi.db"


def migrate(src_path: Path, dst_path: Path):
    if not src_path.exists():
        print(f"❌ Source database not found: {src_path}")
        sys.exit(1)

    # Ensure destination directory exists
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Source: {src_path}")
    print(f"Destination: {dst_path}")
    print()

    src = sqlite3.connect(str(src_path))
    src.row_factory = sqlite3.Row
    dst = sqlite3.connect(str(dst_path))
    dst.row_factory = sqlite3.Row

    # Initialise destination schema if needed
    _init_schema(dst)

    tables = [
        "conversations",
        "messages",
        "entities",
        "facts",
        "relationships",
        "provenance",
        "coverage",
        "agent_state",
    ]

    total_copied = 0
    total_skipped = 0

    for table in tables:
        copied, skipped = _copy_table(src, dst, table)
        total_copied += copied
        total_skipped += skipped
        status = f"  ✓ {table}: {copied} copied"
        if skipped:
            status += f", {skipped} already existed (skipped)"
        print(status)

    dst.commit()
    src.close()
    dst.close()

    print()
    print(f"✅ Migration complete!")
    print(f"   Records copied:  {total_copied}")
    print(f"   Records skipped: {total_skipped}")
    print(f"   Database:        {dst_path}")


def _copy_table(src: sqlite3.Connection, dst: sqlite3.Connection, table: str) -> tuple[int, int]:
    """Copy all rows from src table to dst, skipping duplicates by primary key."""
    try:
        rows = src.execute(f"SELECT * FROM {table}").fetchall()
    except sqlite3.OperationalError:
        # Table doesn't exist in source
        return 0, 0

    if not rows:
        return 0, 0

    cols = rows[0].keys()
    placeholders = ", ".join(["?"] * len(cols))
    col_names = ", ".join(cols)

    copied = 0
    skipped = 0

    for row in rows:
        try:
            dst.execute(
                f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",
                tuple(row),
            )
            copied += 1
        except sqlite3.IntegrityError:
            # Primary key or unique constraint — record already exists, skip
            skipped += 1

    return copied, skipped


def _init_schema(db: sqlite3.Connection):
    """Create tables if they don't exist yet (same schema as Biographer/Remi)."""
    db.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
        CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);

        CREATE TABLE IF NOT EXISTS entities (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            relationship TEXT,
            family_role TEXT,
            description TEXT DEFAULT '',
            properties TEXT DEFAULT '{}',
            confidence REAL DEFAULT 0.5,
            mention_count INTEGER DEFAULT 1,
            first_mentioned_at TEXT,
            last_mentioned_at TEXT,
            is_verified INTEGER DEFAULT 0,
            is_suppressed INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS facts (
            id TEXT PRIMARY KEY,
            subject_entity_id TEXT REFERENCES entities(id) ON DELETE SET NULL,
            predicate TEXT NOT NULL DEFAULT 'stated',
            value TEXT NOT NULL,
            category TEXT NOT NULL,
            date_year INTEGER,
            date_month INTEGER,
            date_precision TEXT DEFAULT 'unknown',
            era TEXT,
            confidence REAL DEFAULT 0.5,
            mention_count INTEGER DEFAULT 1,
            is_verified INTEGER DEFAULT 0,
            is_anchor INTEGER DEFAULT 0,
            significance INTEGER DEFAULT 3,
            is_suppressed INTEGER DEFAULT 0,
            suppression_reason TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS relationships (
            id TEXT PRIMARY KEY,
            from_entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            to_entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            relationship_type TEXT NOT NULL,
            is_bidirectional INTEGER DEFAULT 0,
            confidence REAL DEFAULT 0.5,
            source TEXT DEFAULT 'extracted',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(from_entity_id, to_entity_id, relationship_type)
        );

        CREATE TABLE IF NOT EXISTS provenance (
            id TEXT PRIMARY KEY,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            message_id TEXT,
            extraction_method TEXT DEFAULT 'agent',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS coverage (
            category TEXT PRIMARY KEY,
            fact_count INTEGER DEFAULT 0,
            entity_count INTEGER DEFAULT 0,
            avg_confidence REAL DEFAULT 0.0,
            last_discussed_at TEXT,
            coverage_level TEXT DEFAULT 'none',
            era_coverage TEXT DEFAULT '{}',
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS agent_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    db.commit()


def main():
    parser = argparse.ArgumentParser(description="Migrate Biographer DB → Remi DB")
    parser.add_argument(
        "--src",
        default=str(DEFAULT_SRC),
        help=f"Path to biographer.db (default: {DEFAULT_SRC})",
    )
    parser.add_argument(
        "--dst",
        default=str(DEFAULT_DST),
        help=f"Path to remi.db (default: {DEFAULT_DST})",
    )
    args = parser.parse_args()

    migrate(Path(args.src), Path(args.dst))


if __name__ == "__main__":
    main()
