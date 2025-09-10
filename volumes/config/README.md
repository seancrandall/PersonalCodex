This directory stores user preferences and app configuration.

Mounted path in containers: /data/config

Notes
- Do not store secrets here (use Docker secrets or .env for sensitive values).
- Files are JSON for simplicity; override per-user by editing in-place.
- The API and web apps can read from /data/config; defaults are safe.

Files
- preferences.json: UI preferences (theme, font sizing, display toggles).
- ocr.json: OCR defaults (engine, models, languages).
- ingest.json: Ingest pipeline behavior and paths. TXT is the canonical output root (/data/txt); OCR_DIR is deprecated.
- app.json: App-level settings and feature flags.
