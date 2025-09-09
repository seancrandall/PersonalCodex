## Simple pipeline to build/seed/import/normalize/check the Standard Works DB

DB ?= volumes/scripdb/standardworks.db
ROOT ?= src/scripturedb/scriptures
NOTES_DB ?= volumes/notesdb/notes.db
NOTES_SCHEMA ?= src/notesdb/schema.sql

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

validate-notesdb:
    python scripts/validate_notes_passages.py --notes-db $(NOTES_DB) --std-db $(DB)

fill-citations:
	python scripts/validate_notes_passages.py --notes-db $(NOTES_DB) --std-db $(DB) --fill-citations

clean-notesdb:
	rm -f $(NOTES_DB)
	@echo "Removed $(NOTES_DB)"
