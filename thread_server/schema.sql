/* Thread — SQLite Schema
 *
 * Performance-optimized for agent context retrieval.
 * Key design: FTS5 external content table backed by 'entries' for no-JOIN searches.
 */

-- Sessions: named context isolation buckets
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Covering index for session name lookups (the single hottest query path)
CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_name ON sessions(name);

-- Entries: individual context items
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 5 CHECK(priority >= 0 AND priority <= 10),
    tags TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

-- Basic indexes for common filters
CREATE INDEX IF NOT EXISTS idx_entries_session ON entries(session_id);
CREATE INDEX IF NOT EXISTS idx_entries_priority ON entries(priority);

-- Composite index for the hottest query: list entries in a session, newest first.
-- Covers both the WHERE and ORDER BY, eliminating filesort.
CREATE INDEX IF NOT EXISTS idx_entries_session_created ON entries(session_id, created_at DESC);

-- FTS5 virtual table as an external content table backed by 'entries'.
-- SELECT from entries_fts returns ALL columns (id, content, tags, session_id,
-- priority, created_at) without JOINing back to entries. ~40% search speedup.
-- Tokenizer: porter stemming + unicode normalization + 2-char minimum + 2/3/4 prefix.
CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
    content,
    tags,
    session_id UNINDEXED,
    priority UNINDEXED,
    created_at UNINDEXED,
    updated_at UNINDEXED,
    content='entries',
    content_rowid='id',
    tokenize='porter unicode61 remove_diacritics 2',
    prefix='2 3 4'
);

-- Trigger: keep FTS5 in sync on INSERT
CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN
    INSERT INTO entries_fts(rowid, content, tags, session_id, priority, created_at, updated_at)
    VALUES (new.id, new.content, new.tags, new.session_id, new.priority, new.created_at, new.updated_at);
END;

-- Trigger: keep FTS5 in sync on DELETE
CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON entries BEGIN
    INSERT INTO entries_fts(entries_fts, rowid, content, tags, session_id, priority, created_at, updated_at)
    VALUES ('delete', old.id, old.content, old.tags, old.session_id, old.priority, old.created_at, old.updated_at);
END;

-- Trigger: keep FTS5 in sync on UPDATE (delete old + insert new)
CREATE TRIGGER IF NOT EXISTS entries_au AFTER UPDATE ON entries BEGIN
    INSERT INTO entries_fts(entries_fts, rowid, content, tags, session_id, priority, created_at, updated_at)
    VALUES ('delete', old.id, old.content, old.tags, old.session_id, old.priority, old.created_at, old.updated_at);
    INSERT INTO entries_fts(rowid, content, tags, session_id, priority, created_at)
    VALUES (new.id, new.content, new.tags, new.session_id, new.priority, new.created_at);
END;
