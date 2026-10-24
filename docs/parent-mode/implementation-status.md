# Parent-mode implementation status

The feature is **functional for game trials; not yet deployed to the tablet**. The Review tile now lists real catalog games (imported at startup from the bootstrap), a row tap launches the actual game in an isolated Firefox kiosk profile, Down/Up returns to an interim editor showing the recorded outcome. Renaming/rating/Keep-Select CTAs are the next UI slice. Parent mode is now reachable in the running launcher: Up/Down/Down opens the grey parent menu, Exit returns to the child home, and Review/Wifi open honest placeholder screens. The old launcher behavior (tiles, fallbacks, voices, time limits) is preserved behind the same window. Not deployed yet — run `leo_deploy` to test on the tablet. The legacy Down/Up watcher still runs alongside until the cutover task.

## Completed execution-plan tasks

| Task | Implemented scope | Files |
|---|---|---|
| parent-1 | Editable Python package, development dependencies, pytest/Ruff/mypy configuration, temporary storage/D-Bus isolation, network guards, inert clock/process fixtures and explicit hardware/display opt-ins | `app/pyproject.toml`, `app/tests/conftest.py`, `test_harness.py`, `.gitignore` |
| parent-5 | Immutable catalog values; media/orientation/dimension-evidence enums; conservative HTTP(S) normalization; stable UUIDv5 identities; launch overrides do not change source identity | `domain/catalog.py`, `test_catalog_model.py` |
| parent-6 | Validated review drafts, home-slot DTOs, review enums/service protocols, launch roles/outcomes/ownership contexts and typed errors | `domain/reviews.py`, `domain/sessions.py`, `domain/errors.py`, `test_review_model.py` |
| parent-8 | Private XDG/file initialization, WAL/FULL/foreign-key/busy settings, caller-owned transactions and thread confinement | `storage/database.py`, `integration/test_database.py` |
| parent-9 | Version-1 provider/game/import-history tables with source identity uniqueness, restricted foreign keys, UUID/rating/revision/dimension/JSON constraints and migration registry | `storage/schema/v001_catalog.py`, `integration/test_catalog_schema.py` |
| parent-10 | Version-2 home/history tables: positions 1–9, unique game assignment, exclusive game/legacy occupancy, delete-blocking trigger, role/outcome/started/ended invariants and indexed unfinished sessions | `storage/schema/v002_state.py`, `integration/test_state_schema.py` |
| parent-21 | Both three-tap patterns, injected monotonic clock, configurable gap/window/cooldown, consumed matches, longest valid suffix, reset reasons and noise handling | `domain/gestures.py`, `test_gestures.py` |
| parent-87 | Ordered/checksummed migration batches, UTC history, fail-closed schema validation, pre-upgrade SQLite backups and atomic schema/data/history upgrades | `storage/migrations.py`, `integration/test_migrations.py` |
| parent-88 | Fault tests for corruption, read-only/full/locked writes, rollback, failed/interrupted/timed-out backups, history mismatch, symlinks and cross-thread misuse | `integration/test_storage_failures.py` |
| parent-89 | Validated immutable provider/import DTOs; parameterized provider upsert and append-only import history; shared transaction/error boundary; flexible source adapters (legacy boolean orientation stays unknown; sizes require evidence) | `domain/catalog_metadata.py`, `storage/catalog_metadata.py`, `storage/_repository.py`, `integration/test_catalog_metadata.py` |
| parent-90 | Complete immutable game records with parent/source fields, launch overrides, arbitrary JSON-object provenance, nullable rating, evidence and UTC timestamps; insert/get/list/source-refresh without hidden commits or review replacement | `domain/catalog_records.py`, `storage/catalog.py`, `integration/test_catalog_repository.py` |
| parent-13 | Atomic/idempotent source import: flexible-shape source adapter, provider upserts, source-field-only refreshes, preserved parent decisions/tombstones, duplicate/unlisted-provider rejection, import-history reports | `storage/catalog_import.py`, `integration/test_catalog_import.py` |
| parent-12 | Versioned `catalog/bootstrap.json` (109 games/14 providers) generated deterministically from the flexible discovery input with explicit unknown orientation, nullable dimensions carrying provider-level evidence (Gulli popup, Starfall design, Lumni inferred), self-checksum, and structural validation via `--check` (tampered checksum, duplicate identity, unknown provider) | `tools/prepare_catalog.py`, `catalog/bootstrap.json`, `unit/test_prepare_catalog.py` |

| parent-7 | Launcher extracted into `leo_kiosk/ui/window.py` + `application.py` with injected popen/clock/player/exit hooks; behavior preserved (tiles, voices, fallbacks, `.app-pid` 0600, corner, time limits); `launcher.py` is a thin entry point | `leo_kiosk/ui/window.py`, `leo_kiosk/application.py`, `launcher.py`, `ui/test_shell.py` |
| parent-19 | Frozen review queue: snapshot ordering, skip-without-wrap, advance-past-by-identity, explicit end | `domain/review_queue.py`, `unit/test_review_queue.py` |
| parent-29 | Pure route controller implementing the architecture table (UDD/DDU/DU per context), trial-game context, dirty-editor confirmation, portal/Wifi destinations | `services/navigation.py`, `unit/test_navigation.py` |
| parent-32 | Shared nine-position tile grid: always nine positions, inert unlabeled blanks, child/parent styling split | `ui/tile_grid.py`, `ui/test_tile_grid.py` |
| parent-33 | Grey parent menu (Review/Wifi/Exit active, six blanks) with retro amber-on-dark styling; Exit navigates, never quits the loop | `ui/parent_home.py`, `ui/test_parent_home.py` |
| parent-15/16/17/18 | Home seeding (nine legacy positions inserted exactly once, trusted-config validation, replacement-proof), joinable transaction scopes, slot primitives (eligibility, occupant-confirmed replacement, move clears old slot first), atomic save_review (metadata + Keep/Select + audit in one txn, stale-revision conflict), atomic delete/restore (tombstone, unselect, never saves draft) | `services/home_seed.py`, `services/home.py`, `services/reviews.py`, `storage/home.py`, schema v003, `integration/test_review_transactions.py` |
| parent-22 | Volume input monitor: evdev sources (capability-filtered), GLib fd watches, pump-based event drain, typed scan errors; verified end-to-end through GLib using synthetic input_event pipes | `adapters/input.py`, `unit/test_input_monitor.py` |
| Wiring (part of composition) | Parent mode reachable in the running window: stack pages (child/parent/review/wifi placeholders), gesture dispatch through the navigation controller, Exit returns to child home; gestures ignored while an app is foregrounded | `application.py`, `ui/window.py` (attach_pages/show_page), `ui/test_parent_wiring.py` |
Implementation paths are under `app/leo_kiosk/`; test files are under `app/tests/`, with unqualified earlier test filenames in `unit/`. Repositories persist data when explicitly called; no repository or database is opened by the unchanged launcher.
| parent-14 | Catalog query service: status derivation (new/tested/reviewed/selected derived from slots), game-only eligibility, deterministic ordering, evidence labels | `services/catalog.py`, `unit/test_catalog_service.py` |
| Startup import | `catalog/bootstrap.json` loaded through a checksum-gated source adapter at startup; storage failure degrades to legacy tiles only | `adapters/catalog_source.py`, `application.py` |
| parent-23/24 | Private per-trial Firefox profiles (0700, kiosk user.js prefs, sandbox/TLS untouched, persistent child profile) and argv builder (no-remote/new-instance/profile/kiosk, HTTP(S)-only) | `adapters/browser_profiles.py`, `adapters/firefox.py`, `unit/test_trial_sessions.py` |
| Trial sessions | Token-owned launch/stop/exit with TERM→bounded-KILL, poll-based exit watch, spawn-failure recording, profile cleanup, session history; pending-outcome wins over exit-code heuristic | `services/sessions.py`, `storage/sessions.py`, `unit/test_trial_sessions.py` |
| Review UI (interim) | Review list rows (name + status badge) launch real trials; Down/Up swaps the recognizer and returns to an interim editor page showing the recorded outcome (rename/rating/CTAs pending) | `ui/review_list.py`, `application.py` |

### Plan refinement and source-format decision

- The original parent-8 was split into parent-8/87/88 for connection setup, migrations/backups and fault coverage. Parent-9 was split into parent-9/89/90 for schema, provider/import metadata and game persistence. Each slice targets approximately 300 implementation/test lines.
- [specs.md](../../specs.md) is the authoritative **90-task** graph; the original 68-task backlog/JSON are marked historical.
- Per the owner, `web-games.json` has **no fixed format or permanent-file requirement**. SQLite is authoritative; source JSON may be rearranged or deleted after verified import. The old exact six-key/immutable-snapshot contracts are superseded.
- The original file remains unchanged for now because the audit/bootstrap/import tasks are not done. A versioned bootstrap asset will seed new installations without requiring that filename or overwriting parent decisions. Useful provenance/checksums belong in SQLite/bootstrap metadata, not a mandatory old source layout.

## Verification

Executed in a project-local virtual environment using Python 3.14.8 and SQLite 3.54.0:

- Unit/property/integration/UI tests: **340 passed** (321 prior plus 19 catalog-query, bootstrap-source, profile/firefox and trial-session tests). Bootstrap checks cover deterministic regeneration, legacy-boolean→unknown orientation mapping, provider-level dimension evidence, `--check` tamper/duplicate/unknown-provider detection, and unmappable source rejection (unknown provider name, non-HTTP(S) URL, invalid type label, unattributed sizes on providers without a recorded evidence caveat). State checks cover position/uniqueness/exclusive-occupancy constraints, delete-blocked seeded rows and game identity, role/ownership matching, outcome/ended/started consistency, unfinished-session detection and reopen repeatability. Import checks cover fresh/updated/unchanged/reimported sources, preserved reviews and tombstones, unlisted providers, duplicate source identities and unchanged totals on invalid input.
- Ruff lint/formatting: pass; lint also covers unchanged legacy scripts.
- Strict mypy: pass for all 17 package source files.
- Wheel build: pass; schema/repository modules are included and no mutable database/backup artifacts are packaged.
- Catalog checks cover schema upgrade/reopen, constraints, immutable DTOs, parameter safety, provider/import history, missing/invalid records, stable-ID integrity, null/zero ratings, launch overrides, arbitrary provenance, tombstones, source evidence and caller rollback. Binding overflow is translated into a storage error rather than a raw crash.
- Existing fault/WAL backup tests still pass. All databases are temporary test files; no host disk was filled, no networking was configured and no live catalog was populated.

Reproduce with [development.md](development.md). No target-device or GTK integration acceptance has been performed.

## Not yet complete

- parent-2 platform audit, parent-3 touch portal spike and parent-4 libnm/iwd permission spike require actual target measurements. No assumptions have been recorded as passes.
- Source audit and the versioned bootstrap asset are done (provenance/exclusions, `catalog/bootstrap.json` with self-checksum); the import service consumes source adapters and still needs wiring to bootstrap.json at startup plus review/selection transactions and the approved game-list service; home/session storage exists without repository wrappers.
- Parent GTK screens, evdev integration, owned Firefox sessions, Wi-Fi controls and portal implementation are pending.
- Repository `list_records()` is a source-record listing of all media types, not a playable/approved queue. It hides tombstones by default; explicit lookup does not restore a tombstone. Selection is not duplicated in the game table.
- The production `backwatch.py` still runs alongside the new in-app input monitor (duplicate Down/Up behavior until cutover); entering parent mode from inside a legacy app is not wired yet (review trials themselves are fully interruptible with Down/Up); the review editor is interim (no rename/rating/CTAs yet); Wifi remains a placeholder pending libnm work.
- No installer change beyond the GRUB block, no root configuration beyond what the installer applies, and no Wi-Fi service, polkit policy or input permissions changed.

## Next independent slices

- parent-7: extract the GTK shell while retaining current behavior.
- parent-11: audit available source records and provenance without freezing the source format.
- parent-12/13: prepare a versioned bootstrap, verify idempotent SQLite import/reopen and fresh-install seeding, then optionally remove the original JSON and update references.
- parent-7: extract the GTK shell while retaining current behavior.
- parent-2: obtain the actual Surface Go audit before hardware/network integration.

Do not release parent mode until the remaining architecture gates and Surface Go acceptance pass. Full plan: [specs.md](../../specs.md).
