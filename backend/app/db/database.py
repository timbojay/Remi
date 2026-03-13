import aiosqlite
import os
from app.config import settings

_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        os.makedirs(os.path.dirname(settings.DB_PATH), exist_ok=True)
        _db = await aiosqlite.connect(settings.DB_PATH)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA foreign_keys=ON")
    return _db


async def close_db():
    global _db
    if _db is not None:
        await _db.close()
        _db = None


async def init_db():
    db = await get_db()
    await db.executescript("""
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

        CREATE INDEX IF NOT EXISTS idx_messages_conversation
            ON messages(conversation_id);
        CREATE INDEX IF NOT EXISTS idx_messages_timestamp
            ON messages(timestamp);

        -- Unified entities: people, places, books, films, music, organizations
        CREATE TABLE IF NOT EXISTS entities (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            entity_type TEXT NOT NULL CHECK(entity_type IN (
                'person', 'place', 'book', 'film', 'music', 'organization', 'school', 'other'
            )),
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
        CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
        CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);
        CREATE INDEX IF NOT EXISTS idx_entities_suppressed ON entities(is_suppressed);

        -- Atomic biographical facts with provenance
        CREATE TABLE IF NOT EXISTS facts (
            id TEXT PRIMARY KEY,
            subject_entity_id TEXT REFERENCES entities(id) ON DELETE SET NULL,
            predicate TEXT NOT NULL DEFAULT 'stated',
            value TEXT NOT NULL,
            category TEXT NOT NULL CHECK(category IN (
                'identity', 'family', 'education', 'career', 'residence',
                'milestone', 'childhood', 'relationships', 'hobbies',
                'health', 'travel', 'beliefs', 'daily_life', 'challenges', 'dreams'
            )),
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
        CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category);
        CREATE INDEX IF NOT EXISTS idx_facts_subject ON facts(subject_entity_id);
        CREATE INDEX IF NOT EXISTS idx_facts_era ON facts(era);
        CREATE INDEX IF NOT EXISTS idx_facts_verified ON facts(is_verified);
        CREATE INDEX IF NOT EXISTS idx_facts_suppressed ON facts(is_suppressed);

        -- Relationships between entities
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
        CREATE INDEX IF NOT EXISTS idx_rel_from ON relationships(from_entity_id);
        CREATE INDEX IF NOT EXISTS idx_rel_to ON relationships(to_entity_id);

        -- Provenance: links facts/entities to source conversations
        CREATE TABLE IF NOT EXISTS provenance (
            id TEXT PRIMARY KEY,
            target_type TEXT NOT NULL CHECK(target_type IN ('fact', 'entity', 'relationship')),
            target_id TEXT NOT NULL,
            conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            message_id TEXT,
            extraction_method TEXT DEFAULT 'agent',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_provenance_target ON provenance(target_type, target_id);
        CREATE INDEX IF NOT EXISTS idx_provenance_conversation ON provenance(conversation_id);

        -- Coverage: tracks what life domains are well-explored
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

        -- Narratives: story threads grouping related facts
        CREATE TABLE IF NOT EXISTS narratives (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            fact_ids TEXT DEFAULT '[]',
            era TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_narratives_era ON narratives(era);

        -- Question bank: tracks interview questions and follow-ups
        CREATE TABLE IF NOT EXISTS questions (
            id TEXT PRIMARY KEY,
            question_text TEXT NOT NULL,
            category TEXT NOT NULL,
            priority INTEGER DEFAULT 3,
            is_answered INTEGER DEFAULT 0,
            asked_at TEXT,
            answered_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_questions_priority ON questions(priority DESC);
        CREATE INDEX IF NOT EXISTS idx_questions_answered ON questions(is_answered);

        -- Agent persistent state
        CREATE TABLE IF NOT EXISTS agent_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    await db.commit()
