-- SQLite schema for the Standard Works corpus
-- Enables referential integrity and provides a view joining verse + parents.

PRAGMA foreign_keys = ON;

-- Top-level volumes (e.g., Old Testament, New Testament, D&C, Book of Mormon, Pearl of Great Price)
CREATE TABLE IF NOT EXISTS volume (
  id INTEGER PRIMARY KEY,
  VolumeName TEXT NOT NULL UNIQUE
);

-- Books of scripture; for D&C, the single book is "Sections"
CREATE TABLE IF NOT EXISTS book (
  id INTEGER PRIMARY KEY,
  fkVolume INTEGER NOT NULL,
  BookName TEXT NOT NULL,
  BookHeading TEXT,
  CONSTRAINT fk_book_volume FOREIGN KEY (fkVolume)
    REFERENCES volume(id)
    ON UPDATE CASCADE
    ON DELETE CASCADE,
  CONSTRAINT uq_book_name_per_volume UNIQUE (fkVolume, BookName)
);

-- Chapters/Sections within a book
CREATE TABLE IF NOT EXISTS chapter (
  id INTEGER PRIMARY KEY,
  fkBook INTEGER NOT NULL,
  ChapterNumber TEXT NOT NULL,
  ChapterHeading TEXT,
  CONSTRAINT fk_chapter_book FOREIGN KEY (fkBook)
    REFERENCES book(id)
    ON UPDATE CASCADE
    ON DELETE CASCADE,
  CONSTRAINT uq_chapter_number_per_book UNIQUE (fkBook, ChapterNumber)
);

-- Verses within a chapter/section
CREATE TABLE IF NOT EXISTS verse (
  id INTEGER PRIMARY KEY,
  fkChapter INTEGER NOT NULL,
  VerseNumber INTEGER NOT NULL CHECK (VerseNumber > 0),
  VerseContent TEXT NOT NULL,
  CONSTRAINT fk_verse_chapter FOREIGN KEY (fkChapter)
    REFERENCES chapter(id)
    ON UPDATE CASCADE
    ON DELETE CASCADE,
  CONSTRAINT uq_verse_number_per_chapter UNIQUE (fkChapter, VerseNumber)
);

-- Footnotes for a verse (letter + text). A footnote has an originating verse
-- and may also be attached to additional verses via the footnote_verse table.
CREATE TABLE IF NOT EXISTS footnote (
  id INTEGER PRIMARY KEY,
  fkVerse INTEGER NOT NULL,
  FootnoteLetter TEXT,
  FootnoteText TEXT,
  CONSTRAINT fk_footnote_origin_verse FOREIGN KEY (fkVerse)
    REFERENCES verse(id)
    ON UPDATE CASCADE
    ON DELETE CASCADE
);

-- Junction: associates footnotes with verses (many-to-many)
CREATE TABLE IF NOT EXISTS footnote_verse (
  id INTEGER PRIMARY KEY,
  fkVerse INTEGER NOT NULL,
  fkFootnote INTEGER NOT NULL,
  CONSTRAINT fk_fv_verse FOREIGN KEY (fkVerse)
    REFERENCES verse(id)
    ON UPDATE CASCADE
    ON DELETE CASCADE,
  CONSTRAINT fk_fv_footnote FOREIGN KEY (fkFootnote)
    REFERENCES footnote(id)
    ON UPDATE CASCADE
    ON DELETE CASCADE,
  CONSTRAINT uq_fv UNIQUE (fkVerse, fkFootnote)
);

-- Helpful indexes for joins/lookups
CREATE INDEX IF NOT EXISTS idx_book_fkVolume ON book(fkVolume);
CREATE INDEX IF NOT EXISTS idx_chapter_fkBook ON chapter(fkBook);
CREATE INDEX IF NOT EXISTS idx_verse_fkChapter ON verse(fkChapter);
CREATE INDEX IF NOT EXISTS idx_footnote_fkVerse ON footnote(fkVerse);
CREATE INDEX IF NOT EXISTS idx_fv_fkVerse ON footnote_verse(fkVerse);
CREATE INDEX IF NOT EXISTS idx_fv_fkFootnote ON footnote_verse(fkFootnote);

-- View: each verse with all ancestor metadata
DROP VIEW IF EXISTS allverses;
CREATE VIEW allverses AS
SELECT
  v.id AS verse_id,
  v.VerseNumber,
  v.VerseContent,
  c.id AS chapter_id,
  c.ChapterNumber,
  c.ChapterHeading,
  b.id AS book_id,
  b.BookName,
  b.BookHeading,
  vol.id AS volume_id,
  vol.VolumeName
FROM verse v
JOIN chapter c ON c.id = v.fkChapter
JOIN book b ON b.id = c.fkBook
JOIN volume vol ON vol.id = b.fkVolume
ORDER BY vol.id, b.id, c.id, v.VerseNumber;
