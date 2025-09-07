## Simple pipeline to build/seed/import/normalize/check the Standard Works DB

DB ?= volumes/scripdb/standardworks.db
ROOT ?= src/scripturedb/scriptures

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

