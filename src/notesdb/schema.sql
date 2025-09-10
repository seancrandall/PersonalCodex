-- Personal Codex: Notes Database Schema (SQLite)
-- Location: volumes/notesdb/notes.db (schema kept in src/notesdb/schema.sql)

PRAGMA foreign_keys = ON;

BEGIN;

-- ===============================
-- Core: Files (scanned page images)
-- ===============================
CREATE TABLE IF NOT EXISTS file (
    id              INTEGER PRIMARY KEY,
    path            TEXT NOT NULL UNIQUE, -- container-absolute path (/data/images/...)
    original_filename TEXT,               -- original name at import time (basename)
    sha256          TEXT UNIQUE,
    width_px        INTEGER,
    height_px       INTEGER,
    dpi             INTEGER,
    format          TEXT NOT NULL CHECK (format IN ('png','tiff','jpeg')),
    source          TEXT,
    captured_at     DATETIME,
    ocr_text_path   TEXT,
    ocr_json_path   TEXT,
    fully_processed INTEGER NOT NULL DEFAULT 0 CHECK (fully_processed IN (0,1)),
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ===============================
-- Core: Notes (logical documents) and page membership
-- ===============================
CREATE TABLE IF NOT EXISTS note (
    id              INTEGER PRIMARY KEY,
    content         TEXT NOT NULL,            -- markdown-capable text block
    title           TEXT,
    author          TEXT,
    notebook        TEXT,
    date_created    TEXT,                     -- ISO date YYYY-MM-DD if known
    date_created_precision TEXT CHECK (date_created_precision IN ('day','month','year') OR date_created_precision IS NULL),
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
    metadata_json   TEXT,                     -- JSON1 payload (arbitrary metadata)
    prev_note_id    INTEGER REFERENCES note(id) ON UPDATE CASCADE ON DELETE SET NULL,
    next_note_id    INTEGER UNIQUE REFERENCES note(id) ON UPDATE CASCADE ON DELETE SET NULL,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    CHECK (prev_note_id IS NULL OR prev_note_id <> id),
    CHECK (next_note_id IS NULL OR next_note_id <> id)
);

CREATE TRIGGER IF NOT EXISTS trg_note_updated_at
AFTER UPDATE ON note
FOR EACH ROW
BEGIN
    UPDATE note SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TABLE IF NOT EXISTS note_file (
    note_id         INTEGER NOT NULL REFERENCES note(id) ON DELETE CASCADE,
    file_id         INTEGER NOT NULL REFERENCES file(id) ON DELETE CASCADE,
    page_order      INTEGER,                  -- optional: order of the file within a sequence
    region_bbox_json TEXT,                    -- if the note covers only a region of the page
    PRIMARY KEY (note_id, file_id)
);

CREATE INDEX IF NOT EXISTS idx_note_file_note_order ON note_file(note_id, page_order);
CREATE INDEX IF NOT EXISTS idx_note_file_file ON note_file(file_id);
-- prev/next handled at note level now

-- ===============================
-- Full-Text Search over notes
-- ===============================
CREATE VIRTUAL TABLE IF NOT EXISTS note_fts USING fts5(
    content,
    content='note',
    content_rowid='id',
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS trg_note_ai
AFTER INSERT ON note BEGIN
    INSERT INTO note_fts(rowid, content) VALUES (new.id, new.content);
END;

-- ===============================
-- Note Edit Dates (change history)
-- ===============================
-- Normalized list of edit dates. Stored as ISO date (YYYY-MM-DD).
CREATE TABLE IF NOT EXISTS edit_date (
    id              INTEGER PRIMARY KEY,
    edit_date       TEXT NOT NULL, -- ISO date
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (edit_date)
);

-- Junction: many edit dates per note; a date can apply to many notes
CREATE TABLE IF NOT EXISTS note_edit_date (
    note_id         INTEGER NOT NULL REFERENCES note(id) ON DELETE CASCADE,
    edit_date_id    INTEGER NOT NULL REFERENCES edit_date(id) ON DELETE CASCADE,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (note_id, edit_date_id)
);

CREATE INDEX IF NOT EXISTS idx_note_edit_date_note ON note_edit_date(note_id);
CREATE INDEX IF NOT EXISTS idx_note_edit_date_date ON note_edit_date(edit_date_id);

-- Automatically record a changed date whenever note content updates
CREATE TRIGGER IF NOT EXISTS trg_note_edit_date
AFTER UPDATE OF content ON note
BEGIN
    -- Ensure the edit_date row for today exists
    INSERT OR IGNORE INTO edit_date(edit_date) VALUES (DATE('now'));
    -- Link this note to today's edit_date
    INSERT OR IGNORE INTO note_edit_date(note_id, edit_date_id)
    SELECT NEW.id, ed.id FROM edit_date ed WHERE ed.edit_date = DATE('now');
END;

CREATE TRIGGER IF NOT EXISTS trg_note_ad
AFTER DELETE ON note BEGIN
    INSERT INTO note_fts(note_fts, rowid, content) VALUES('delete', old.id, old.content);
END;

CREATE TRIGGER IF NOT EXISTS trg_note_au_content
AFTER UPDATE OF content ON note BEGIN
    INSERT INTO note_fts(note_fts, rowid, content) VALUES('delete', old.id, old.content);
    INSERT INTO note_fts(rowid, content) VALUES (new.id, new.content);
END;

-- ===============================
-- Scripture Passages (verse ranges)
-- ===============================
-- Note: start_verse_id and end_verse_id refer to verse ids in standardworks.db.
-- SQLite cannot enforce cross-database FKs; validate at application level after ATTACH.
CREATE TABLE IF NOT EXISTS passage (
    id              INTEGER PRIMARY KEY,
    start_verse_id  INTEGER NOT NULL,
    end_verse_id    INTEGER NOT NULL,
    citation        TEXT, -- denormalized label (e.g., '1 Ne. 3:7–9')
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    CHECK (start_verse_id <= end_verse_id),
    UNIQUE (start_verse_id, end_verse_id)
);

CREATE INDEX IF NOT EXISTS idx_passage_start ON passage(start_verse_id);
CREATE INDEX IF NOT EXISTS idx_passage_end ON passage(end_verse_id);

-- Many-to-many: notes to passages
CREATE TABLE IF NOT EXISTS note_passage (
    note_id         INTEGER NOT NULL REFERENCES note(id) ON DELETE CASCADE,
    passage_id      INTEGER NOT NULL REFERENCES passage(id) ON DELETE CASCADE,
    relation        TEXT DEFAULT 'mentions' CHECK (relation IN ('mentions','quotes','comments','alludes')),
    PRIMARY KEY (note_id, passage_id)
);

CREATE INDEX IF NOT EXISTS idx_note_passage_passage ON note_passage(passage_id);

-- Block-level anchors removed; use note_passage exclusively

-- ===============================
-- Tagging
-- ===============================
CREATE TABLE IF NOT EXISTS tag (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    color           TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS note_tag (
    note_id         INTEGER NOT NULL REFERENCES note(id) ON DELETE CASCADE,
    tag_id          INTEGER NOT NULL REFERENCES tag(id) ON DELETE CASCADE,
    PRIMARY KEY (note_id, tag_id)
);

-- Block tags removed; use note_tag exclusively

-- ===============================
-- Note Source (stable mapping from import source to note_id)
-- ===============================
CREATE TABLE IF NOT EXISTS note_source (
    note_id         INTEGER NOT NULL REFERENCES note(id) ON DELETE CASCADE,
    source_key      TEXT NOT NULL UNIQUE,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Transcribed pages removed; text is stored as notes and artifacts live under /data/txt

CREATE TABLE IF NOT EXISTS note_link (
    id              INTEGER PRIMARY KEY,
    from_note_id    INTEGER NOT NULL REFERENCES note(id) ON DELETE CASCADE,
    to_note_id      INTEGER NOT NULL REFERENCES note(id) ON DELETE CASCADE,
    link_type       TEXT NOT NULL DEFAULT 'reference' CHECK (link_type IN ('reference','followup','duplicate','see-also')),
    label           TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (from_note_id, to_note_id, link_type)
);

CREATE INDEX IF NOT EXISTS idx_note_link_from ON note_link(from_note_id);
CREATE INDEX IF NOT EXISTS idx_note_link_to ON note_link(to_note_id);
-- Block-level links removed; use note_link exclusively

-- ===============================
-- Embeddings (for AI search)
-- ===============================
CREATE TABLE IF NOT EXISTS embedding_model (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    dims            INTEGER NOT NULL,
    distance        TEXT NOT NULL CHECK (distance IN ('cosine','l2','dot')),
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (name, dims)
);

CREATE TABLE IF NOT EXISTS note_embedding (
    note_id         INTEGER NOT NULL REFERENCES note(id) ON DELETE CASCADE,
    model_id        INTEGER NOT NULL REFERENCES embedding_model(id) ON DELETE CASCADE,
    vector          BLOB NOT NULL, -- float32 array
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (note_id, model_id)
);
-- Block-level embeddings removed; use note_embedding exclusively

-- ===============================
-- Collections (optional) and key-value metadata
-- ===============================
CREATE TABLE IF NOT EXISTS collection (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS collection_item (
    collection_id   INTEGER NOT NULL REFERENCES collection(id) ON DELETE CASCADE,
    note_id         INTEGER NOT NULL REFERENCES note(id) ON DELETE CASCADE,
    PRIMARY KEY (collection_id, note_id)
);

CREATE TABLE IF NOT EXISTS metadata (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL
);

COMMIT;

--
-- Usage notes:
-- 1) To build notes.db from this schema, run: sqlite3 volumes/notesdb/notes.db < src/notesdb/schema.sql
-- 2) To validate passages against the scripture DB:
--    ATTACH DATABASE 'volumes/scripdb/standardworks.db' AS std;
--    -- Then your application can validate passage.start_verse_id EXISTS in std.verses(id)
-- 3) Preferred image formats for text: PNG (lossless) or TIFF (archival). JPEG accepted but not ideal for OCR.
