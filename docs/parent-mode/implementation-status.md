# Parent-mode implementation status

The feature is **partially implemented, not integrated into the launcher**. Existing child tiles, shortcuts, process launching and system configuration are unchanged. The catalog schema and repositories now exist, but the discovery catalog has not been imported into a live database; home/session schemas, review transactions and UI integration remain pending.

## Completed execution-plan tasks

| Task | Implemented scope | Files |
|---|---|---|
| parent-1 | Editable Python package, development dependencies, pytest/Ruff/mypy configuration, temporary storage/D-Bus isolation, network guards, inert clock/process fixtures and explicit hardware/display opt-ins | `leo-kiosk/pyproject.toml`, `leo-kiosk/tests/conftest.py`, `test_harness.py`, `.gitignore` |
| parent-5 | Immutable catalog values; media/orientation/dimension-evidence enums; conservative HTTP(S) normalization; stable UUIDv5 identities; launch overrides do not change source identity | `domain/catalog.py`, `test_catalog_model.py` |
| parent-6 | Validated review drafts, home-slot DTOs, review enums/service protocols, launch roles/outcomes/ownership contexts and typed errors | `domain/reviews.py`, `domain/sessions.py`, `domain/errors.py`, `test_review_model.py` |
| parent-8 | Private XDG/file initialization, WAL/FULL/foreign-key/busy settings, caller-owned transactions and thread confinement | `storage/database.py`, `integration/test_database.py` |
| parent-9 | Version-1 provider/game/import-history tables with source identity uniqueness, restricted foreign keys, UUID/rating/revision/dimension/JSON constraints and migration registry | `storage/schema/`, `integration/test_catalog_schema.py` |
| parent-21 | Both three-tap patterns, injected monotonic clock, configurable gap/window/cooldown, consumed matches, longest valid suffix, reset reasons and noise handling | `domain/gestures.py`, `test_gestures.py` |
| parent-87 | Ordered/checksummed migration batches, UTC history, fail-closed schema validation, pre-upgrade SQLite backups and atomic schema/data/history upgrades | `storage/migrations.py`, `integration/test_migrations.py` |
| parent-88 | Fault tests for corruption, read-only/full/locked writes, rollback, failed/interrupted/timed-out backups, history mismatch, symlinks and cross-thread misuse | `integration/test_storage_failures.py` |
| parent-89 | Validated immutable provider/import DTOs; parameterized provider upsert and append-only import history; shared transaction/error boundary | `domain/catalog_metadata.py`, `storage/catalog_metadata.py`, `storage/_repository.py`, `integration/test_catalog_metadata.py` |
| parent-90 | Complete immutable game records with parent/source fields, launch overrides, arbitrary JSON-object provenance, nullable rating, evidence and UTC timestamps; insert/get/list without hidden commits or review replacement | `domain/catalog_records.py`, `storage/catalog.py`, `integration/test_catalog_repository.py` |

Implementation paths are under `leo-kiosk/leo_kiosk/`; test files are under `leo-kiosk/tests/`, with unqualified earlier test filenames in `unit/`. Repositories persist data when explicitly called; no repository or database is opened by the unchanged launcher.

### Plan refinement and source-format decision

- The original parent-8 was split into parent-8/87/88 for connection setup, migrations/backups and fault coverage. Parent-9 was split into parent-9/89/90 for schema, provider/import metadata and game persistence. Each slice targets approximately 300 implementation/test lines.
- [specs.md](../../specs.md) is the authoritative **90-task** graph; the original 68-task backlog/JSON are marked historical.
- Per the owner, `web-games.json` has **no fixed format or permanent-file requirement**. SQLite is authoritative; source JSON may be rearranged or deleted after verified import. The old exact six-key/immutable-snapshot contracts are superseded.
- The original file remains unchanged for now because the audit/bootstrap/import tasks are not done. A versioned bootstrap asset will seed new installations without requiring that filename or overwriting parent decisions. Useful provenance/checksums belong in SQLite/bootstrap metadata, not a mandatory old source layout.

## Verification

Executed in a project-local virtual environment using Python 3.14.8 and SQLite 3.54.0:

- Unit/property/integration tests: **209 passed** (143 prior tests plus 66 catalog tests).
- Ruff lint/formatting: pass; lint also covers unchanged legacy scripts.
- Strict mypy: pass for all 17 package source files.
- Wheel build: pass; schema/repository modules are included and no mutable database/backup artifacts are packaged.
- Catalog checks cover schema upgrade/reopen, constraints, immutable DTOs, parameter safety, provider/import history, missing/invalid records, stable-ID integrity, null/zero ratings, launch overrides, arbitrary provenance, tombstones, source evidence and caller rollback. Binding overflow is translated into a storage error rather than a raw crash.
- Existing fault/WAL backup tests still pass. All databases are temporary test files; no host disk was filled, no networking was configured and no live catalog was populated.

Reproduce with [development.md](development.md). No target-device or GTK integration acceptance has been performed.

## Not yet complete

- parent-2 platform audit, parent-3 touch portal spike and parent-4 libnm/iwd permission spike require actual target measurements. No assumptions have been recorded as passes.
- Home/session tables, source audit/bootstrap/import, source-refresh upserts, review/selection transactions and the approved game-list service are pending.
- Parent GTK screens, evdev integration, owned Firefox sessions, Wi-Fi controls and portal implementation are pending.
- Repository `list_records()` is a source-record listing of all media types, not a playable/approved queue. It hides tombstones by default; explicit lookup does not restore a tombstone. Selection is not duplicated in the game table.
- The production watcher still uses the old Down/Up shortcut until integration/cutover. No installer, root configuration, Wi-Fi service, polkit policy, input permissions or physical settings changed.

## Next independent slices

- parent-10: add constrained home slots and launch/review history using the catalog schema.
- parent-11: audit available source records and provenance without freezing the source format.
- parent-12/13: prepare a versioned bootstrap, verify idempotent SQLite import/reopen and fresh-install seeding, then optionally remove the original JSON and update references.
- parent-7: extract the GTK shell while retaining current behavior.
- parent-2: obtain the actual Surface Go audit before hardware/network integration.

Do not release parent mode until the remaining architecture gates and Surface Go acceptance pass. Full plan: [specs.md](../../specs.md).
