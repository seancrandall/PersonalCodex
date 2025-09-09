## Simple pipeline to build/seed/import/normalize/check the Standard Works DB

DB ?= volumes/scripdb/standardworks.db
ROOT ?= src/scripturedb/scriptures
NOTES_DB ?= volumes/notesdb/notes.db
NOTES_SCHEMA ?= src/notesdb/schema.sql
IMAGES_DIR ?= volumes/images

.PHONY: init-db seed import normalize summary check pipeline clean-db

init-db:
	python scripts/init_standardworks_db.py --db $(DB)

seed: init-db
	python scripts/seed_standardworks.py --db $(DB)

import: seed
	python scripts/import_scriptures.py --db $(DB) --root $(ROOT) --clear-chapter

normalize:
	python scripts/normalize_verses.py --db $(DB)
	python scripts/normalize_metadata.py --db $(DB)

summary:
	python scripts/summary_standardworks.py --db $(DB)

check:
	python scripts/check_normalization.py --db $(DB)

pipeline: import normalize summary check

clean-db:
	rm -f $(DB)
	@echo "Removed $(DB)"

# ------------------------------
# Notes DB (host): build and validate
# ------------------------------
.PHONY: notesdb validate-notesdb fill-citations clean-notesdb

notesdb:
	mkdir -p $(dir $(NOTES_DB))
	sqlite3 $(NOTES_DB) < $(NOTES_SCHEMA)
	@echo "Built $(NOTES_DB) from $(NOTES_SCHEMA)"

## Migrate notesdb to add next/prev pointers for images and transcribed pages
.PHONY: migrate-notesdb-links
migrate-notesdb-links:
	python scripts/migrate_notesdb_add_page_links.py --db $(NOTES_DB)

## Rebuild next/prev pointers for existing data
.PHONY: rebuild-page-links
rebuild-page-links:
	python scripts/rebuild_page_links.py --db $(NOTES_DB)

## Mark files fully processed
.PHONY: mark-processed-ocr
mark-processed-ocr:
	python scripts/mark_files_processed.py --db $(NOTES_DB) --all-ocr

validate-notesdb:
	python scripts/validate_notes_passages.py --notes-db $(NOTES_DB) --std-db $(DB)

## Write OCR outputs into notes.db using manifest or paths
.PHONY: notesdb-write
notesdb-write:
	@test -n "$(MANIFEST)$(PATHS)" || (echo "Set MANIFEST=/path/to/moved_images.json or PATHS='img1 img2' [ORIGINAL=name]" && exit 1)
	volumes/bin/notesdb-write --db $(NOTES_DB) $(if $(MANIFEST),--manifest $(MANIFEST),) $(if $(PATHS),--paths $(PATHS),) --images-dir $(IMAGES_DIR) $(if $(ORIGINAL),--original-name $(ORIGINAL),)

## Assemble note.raw_text and metadata_json from pages
.PHONY: notesdb-assemble
notesdb-assemble:
	volumes/bin/notesdb-assemble --db $(NOTES_DB) $(if $(NOTE_ID),--note-id $(NOTE_ID),) $(if $(ONLY_MISSING),--only-missing,) $(if $(OVERWRITE),--overwrite,)

fill-citations:
	python scripts/validate_notes_passages.py --notes-db $(NOTES_DB) --std-db $(DB) --fill-citations

clean-notesdb:
	rm -f $(NOTES_DB)
	@echo "Removed $(NOTES_DB)"
