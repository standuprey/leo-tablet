# Parent-mode implementation status

The feature is **partially implemented, not integrated into the launcher**. Existing child tiles, shortcuts, process launching and system configuration are unchanged. The original discovery file is unchanged. SQLite startup/migration infrastructure now exists, but application game/home schemas and review persistence are not yet implemented.

## Completed execution-plan tasks

| Task | Implemented scope | Files |
|---|---|---|
| parent-1 | Editable Python package, development dependencies, pytest/Ruff/mypy configuration, temporary storage/D-Bus isolation, network guards, inert clock/process fixtures and explicit hardware/display opt-ins | `leo-kiosk/pyproject.toml`, `leo-kiosk/tests/conftest.py`, `test_harness.py`, `.gitignore` |
| parent-5 | Immutable catalog values; media/orientation/dimension-evidence enums; conservative HTTP(S) normalization; stable UUIDv5 identities; launch-URL overrides do not change source identity | `leo-kiosk/leo_kiosk/domain/catalog.py`, `test_catalog_model.py` |
| parent-6 | Validated review drafts, home-slot DTOs, review enums/service protocols, launch roles/outcomes/ownership contexts and typed errors | `domain/reviews.py`, `domain/sessions.py`, `domain/errors.py`, `test_review_model.py` |
| parent-8 | Private XDG/file initialization, WAL/FULL/foreign-key/busy settings, parameterized transaction scopes and thread confinement | `storage/database.py`, `integration/test_database.py` |
| parent-21 | Both three-tap patterns, injected monotonic clock, configurable gap/window/cooldown, consumed matches, longest valid suffix, reset reasons and noise handling | `domain/gestures.py`, `test_gestures.py` |
| parent-87 | Ordered/checksummed migration batches, UTC history, fail-closed schema validation, pre-upgrade SQLite backups, complete-copy flushing and atomic schema/data/history upgrades | `storage/migrations.py`, `integration/test_migrations.py` |
| parent-88 | Storage fault/invariant tests: corruption, read-only/full/locked writes, upgrade rollback, failed/interrupted/timed-out backups, history mismatch, symlink rejection and cross-thread misuse | `integration/test_storage_failures.py` |

Implementation paths are under `leo-kiosk/leo_kiosk/`; test files are under `leo-kiosk/tests/`, with unqualified earlier test filenames in `unit/`. Service protocols are interfaces only; GTK, application repositories and owned process-control adapters remain pending.

### Plan refinement

The original parent-8 combined startup, migrations/backups and fault coverage. It has been split into parent-8, parent-87 and parent-88 so each implementation/test slice stays below approximately 300 lines. Parent-9 now depends on parent-88. [specs.md](../../specs.md) is the authoritative **88-task** execution plan; the older 68-task backlog remains background documentation.

## Verification

Executed in a project-local virtual environment using Python 3.14.8 and SQLite 3.54.0:

- Unit/property/integration tests: **143 passed** (93 existing domain/harness tests plus 50 storage tests).
- Ruff lint and formatting: pass for the new code; lint also covers the unchanged legacy scripts.
- Strict mypy: pass for all 10 package source files, including storage.
- Storage tests use temporary files only; the WAL backup test verifies that a committed row absent from the main file snapshot is retained by SQLite backup.
- Storage failures are real SQLite constraint/read-only/lock/page-limit errors or explicit bounded fault injections; no host disk was filled and no actual application database was created.

Reproduce with the commands in [development.md](development.md). No target-device or GTK integration acceptance has been performed.

## Not yet complete

- parent-2 platform audit, parent-3 touch portal spike and parent-4 libnm/iwd permission spike require measured target-device evidence. No assumptions have been recorded as passes.
- Application catalog/home/session tables, repositories, catalog normalization/import and review transactions remain pending. `open_database()` currently initializes only migration infrastructure unless supplied trusted batches.
- Parent GTK screens, evdev integration, owned Firefox sessions, Wi-Fi controls and portal implementation remain pending.
- New gestures are only a tested domain recognizer. The production watcher still uses the old Down/Up shortcut until the planned integration/cutover tasks are completed.
- No installer, root configuration, Wi-Fi service, polkit policy, input permissions or physical device setting was changed. No backup restore/retention UI is implemented.

## Next independent slices

- parent-9: add the provider/game/import-history schema and catalog repository using the tested migration runner.
- parent-7: extract the GTK shell while retaining current behavior.
- parent-11: audit discovery records/provenance before generating a playable catalog.
- parent-2: obtain the actual Surface Go audit before hardware/network integration.

Do not release parent mode until the remaining architecture gates and Surface Go acceptance tasks pass. Full plan: [specs.md](../../specs.md).
