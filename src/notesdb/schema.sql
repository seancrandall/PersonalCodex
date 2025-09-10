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
    title           TEXT,
    author          TEXT,
    notebook        TEXT,
    date_created    TEXT, -- ISO date YYYY-MM-DD if known
    date_created_precision TEXT CHECK (date_created_precision IN ('day','month','year') OR date_created_precision IS NULL),
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
    raw_text        TEXT,
    metadata_json   TEXT, -- JSON1 payload (arbitrary metadata)
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
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
    page_order      INTEGER NOT NULL, -- order of the file within the note (1-based recommended)
    region_bbox_json TEXT,            -- if the note covers only a region of the page
    -- Optional linked-list navigation within a note
    prev_file_id    INTEGER REFERENCES file(id) ON DELETE SET NULL,
    next_file_id    INTEGER REFERENCES file(id) ON DELETE SET NULL,
    PRIMARY KEY (note_id, file_id)
);

CREATE INDEX IF NOT EXISTS idx_note_file_note_order ON note_file(note_id, page_order);
CREATE INDEX IF NOT EXISTS idx_note_file_file ON note_file(file_id);
CREATE INDEX IF NOT EXISTS idx_note_file_prev ON note_file(note_id, prev_file_id);
CREATE INDEX IF NOT EXISTS idx_note_file_next ON note_file(note_id, next_file_id);

-- ===============================
-- Content Kernel: Blocks (paragraph/line/etc.)
-- ===============================
CREATE TABLE IF NOT EXISTS note_block (
    id              INTEGER PRIMARY KEY,
    note_id         INTEGER NOT NULL REFERENCES note(id) ON DELETE CASCADE,
    file_id         INTEGER REFERENCES file(id),
    page_number     INTEGER,                  -- 1-based within the note
    block_order     INTEGER NOT NULL,         -- order within the note
    block_type      TEXT NOT NULL CHECK (block_type IN (
                        'paragraph','line','block','heading','list','quote','footnote'
                    )),
    content         TEXT NOT NULL,
    bbox_json       TEXT,                     -- {x0,y0,x1,y1} in image coordinates
    confidence      REAL,
    tokens          INTEGER,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_note_block_note_order ON note_block(note_id, block_order);
CREATE INDEX IF NOT EXISTS idx_note_block_file ON note_block(file_id);

-- Full-Text Search over note_block.content (FTS5 external content)
CREATE VIRTUAL TABLE IF NOT EXISTS note_block_fts USING fts5(
    content,
    content='note_block',
    content_rowid='id',
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS trg_note_block_ai
AFTER INSERT ON note_block BEGIN
    INSERT INTO note_block_fts(rowid, content) VALUES (new.id, new.content);
END;

-- ===============================
-- Block Edit Dates (change history)
-- ===============================
-- Normalized list of edit dates. Stored as ISO date (YYYY-MM-DD).
CREATE TABLE IF NOT EXISTS edit_date (
    id              INTEGER PRIMARY KEY,
    edit_date       TEXT NOT NULL, -- ISO date
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (edit_date)
);

-- Junction: many edit dates per block; a date can apply to many blocks
CREATE TABLE IF NOT EXISTS block_edit_date (
    note_block_id   INTEGER NOT NULL REFERENCES note_block(id) ON DELETE CASCADE,
    edit_date_id    INTEGER NOT NULL REFERENCES edit_date(id) ON DELETE CASCADE,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (note_block_id, edit_date_id)
);

CREATE INDEX IF NOT EXISTS idx_block_edit_date_block ON block_edit_date(note_block_id);
CREATE INDEX IF NOT EXISTS idx_block_edit_date_date ON block_edit_date(edit_date_id);

-- Automatically record a changed date whenever block content updates
CREATE TRIGGER IF NOT EXISTS trg_note_block_edit_date
AFTER UPDATE OF content ON note_block
BEGIN
    -- Ensure the edit_date row for today exists
    INSERT OR IGNORE INTO edit_date(edit_date) VALUES (DATE('now'));
    -- Link this block to today's edit_date
    INSERT OR IGNORE INTO block_edit_date(note_block_id, edit_date_id)
    SELECT NEW.id, ed.id FROM edit_date ed WHERE ed.edit_date = DATE('now');
END;

CREATE TRIGGER IF NOT EXISTS trg_note_block_ad
AFTER DELETE ON note_block BEGIN
    INSERT INTO note_block_fts(note_block_fts, rowid, content) VALUES('delete', old.id, old.content);
END;

CREATE TRIGGER IF NOT EXISTS trg_note_block_au
AFTER UPDATE OF content ON note_block BEGIN
    INSERT INTO note_block_fts(note_block_fts) VALUES('rebuild');
    -- Alternatively, a delete+insert pair per row; 'rebuild' is simple but heavier.
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

-- Block-level passage anchors
CREATE TABLE IF NOT EXISTS block_passage (
    note_block_id   INTEGER NOT NULL REFERENCES note_block(id) ON DELETE CASCADE,
    passage_id      INTEGER NOT NULL REFERENCES passage(id) ON DELETE CASCADE,
    relation        TEXT,
    PRIMARY KEY (note_block_id, passage_id)
);

CREATE INDEX IF NOT EXISTS idx_block_passage_passage ON block_passage(passage_id);

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

CREATE TABLE IF NOT EXISTS block_tag (
    note_block_id   INTEGER NOT NULL REFERENCES note_block(id) ON DELETE CASCADE,
    tag_id          INTEGER NOT NULL REFERENCES tag(id) ON DELETE CASCADE,
    PRIMARY KEY (note_block_id, tag_id)
);

-- ===============================
-- Note Source (stable mapping from import source to note_id)
-- ===============================
CREATE TABLE IF NOT EXISTS note_source (
    note_id         INTEGER NOT NULL REFERENCES note(id) ON DELETE CASCADE,
    source_key      TEXT NOT NULL UNIQUE,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ===============================
-- Transcribed Pages (OCR/plain text per page)
-- ===============================
-- Represents page-level transcriptions with optional linked-list navigation.
CREATE TABLE IF NOT EXISTS transcribed_page (
    id              INTEGER PRIMARY KEY,
    note_id         INTEGER NOT NULL REFERENCES note(id) ON DELETE CASCADE,
    file_id         INTEGER REFERENCES file(id) ON DELETE SET NULL,
    page_order      INTEGER NOT NULL,           -- position within the note
    page_date       TEXT,                       -- ISO date YYYY-MM-DD inferred for this page
    page_date_precision TEXT CHECK (page_date_precision IN ('day','month','year') OR page_date_precision IS NULL),
    text            TEXT,                       -- plain text transcription
    json_path       TEXT,                       -- optional JSON with tokens/bboxes/confidence
    prev_id         INTEGER REFERENCES transcribed_page(id) ON DELETE SET NULL,
    next_id         INTEGER UNIQUE REFERENCES transcribed_page(id) ON DELETE SET NULL,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (note_id, page_order),
    CHECK (prev_id IS NULL OR prev_id <> id),
    CHECK (next_id IS NULL OR next_id <> id)
);

CREATE INDEX IF NOT EXISTS idx_transcribed_page_note_order ON transcribed_page(note_id, page_order);
CREATE INDEX IF NOT EXISTS idx_transcribed_page_file ON transcribed_page(file_id);
CREATE INDEX IF NOT EXISTS idx_transcribed_page_date ON transcribed_page(page_date);

-- ===============================
-- Cross-References (Backlinks)
-- ===============================
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

CREATE TABLE IF NOT EXISTS note_block_link (
    id              INTEGER PRIMARY KEY,
    from_block_id   INTEGER NOT NULL REFERENCES note_block(id) ON DELETE CASCADE,
    to_block_id     INTEGER NOT NULL REFERENCES note_block(id) ON DELETE CASCADE,
    label           TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (from_block_id, to_block_id)
);

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

CREATE TABLE IF NOT EXISTS block_embedding (
    note_block_id   INTEGER NOT NULL REFERENCES note_block(id) ON DELETE CASCADE,
    model_id        INTEGER NOT NULL REFERENCES embedding_model(id) ON DELETE CASCADE,
    vector          BLOB NOT NULL,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (note_block_id, model_id)
);

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
