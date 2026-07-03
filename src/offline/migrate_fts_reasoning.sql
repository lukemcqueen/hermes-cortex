-- migrate_fts_reasoning.sql
-- Add reasoning + reasoning_content to FTS5 indexes
-- Hermes Agent state.db: the FTS triggers on messages only index content,
-- tool_name, and tool_calls — but assistant reasoning is stored in the
-- reasoning/reasoning_content columns. This means ~66% of debugging signal
-- is invisible to FTS search (session-mine, etc.).
--
-- Usage: sqlite3 ~/.hermes/state.db < migrate_fts_reasoning.sql

-- 1. Drop old triggers
DROP TRIGGER IF EXISTS messages_fts_insert;
DROP TRIGGER IF EXISTS messages_fts_delete;
DROP TRIGGER IF EXISTS messages_fts_update;
DROP TRIGGER IF EXISTS messages_fts_trigram_insert;
DROP TRIGGER IF EXISTS messages_fts_trigram_delete;
DROP TRIGGER IF EXISTS messages_fts_trigram_update;

-- 2. Recreate with reasoning + reasoning_content
CREATE TRIGGER messages_fts_insert AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (
        new.id,
        COALESCE(new.content, '') || ' ' || COALESCE(new.reasoning, '') || ' ' || COALESCE(new.reasoning_content, '') || ' ' || COALESCE(new.tool_name, '') || ' ' || COALESCE(new.tool_calls, '')
    );
END;

CREATE TRIGGER messages_fts_delete AFTER DELETE ON messages BEGIN
    DELETE FROM messages_fts WHERE rowid = old.id;
END;

CREATE TRIGGER messages_fts_update AFTER UPDATE ON messages BEGIN
    DELETE FROM messages_fts WHERE rowid = old.id;
    INSERT INTO messages_fts(rowid, content) VALUES (
        new.id,
        COALESCE(new.content, '') || ' ' || COALESCE(new.reasoning, '') || ' ' || COALESCE(new.reasoning_content, '') || ' ' || COALESCE(new.tool_name, '') || ' ' || COALESCE(new.tool_calls, '')
    );
END;

CREATE TRIGGER messages_fts_trigram_insert AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts_trigram(rowid, content) VALUES (
        new.id,
        COALESCE(new.content, '') || ' ' || COALESCE(new.reasoning, '') || ' ' || COALESCE(new.reasoning_content, '') || ' ' || COALESCE(new.tool_name, '') || ' ' || COALESCE(new.tool_calls, '')
    );
END;

CREATE TRIGGER messages_fts_trigram_delete AFTER DELETE ON messages BEGIN
    DELETE FROM messages_fts_trigram WHERE rowid = old.id;
END;

CREATE TRIGGER messages_fts_trigram_update AFTER UPDATE ON messages BEGIN
    DELETE FROM messages_fts_trigram WHERE rowid = old.id;
    INSERT INTO messages_fts_trigram(rowid, content) VALUES (
        new.id,
        COALESCE(new.content, '') || ' ' || COALESCE(new.reasoning, '') || ' ' || COALESCE(new.reasoning_content, '') || ' ' || COALESCE(new.tool_name, '') || ' ' || COALESCE(new.tool_calls, '')
    );
END;

-- 3. Re-populate FTS indexes from current data
DELETE FROM messages_fts;
INSERT INTO messages_fts(rowid, content)
SELECT id,
  COALESCE(content, '') || ' ' || COALESCE(reasoning, '') || ' ' ||
  COALESCE(reasoning_content, '') || ' ' || COALESCE(tool_name, '') || ' ' ||
  COALESCE(tool_calls, '')
FROM messages;

DELETE FROM messages_fts_trigram;
INSERT INTO messages_fts_trigram(rowid, content)
SELECT id,
  COALESCE(content, '') || ' ' || COALESCE(reasoning, '') || ' ' ||
  COALESCE(reasoning_content, '') || ' ' || COALESCE(tool_name, '') || ' ' ||
  COALESCE(tool_calls, '')
FROM messages;

-- 4. Verify
SELECT 'FTS rebuild complete:' as info;
SELECT '  messages_fts: ' || COUNT(*) || ' rows' FROM messages_fts;
SELECT '  messages_fts_trigram: ' || COUNT(*) || ' rows' FROM messages_fts_trigram;
