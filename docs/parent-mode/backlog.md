# Implementation backlog: parent mode, review and Wi-Fi

Status: historical 68-task sizing reference. The authoritative execution graph is [specs.md](../../specs.md); progress is in [implementation-status.md](implementation-status.md). Architecture: [architecture.md](architecture.md). Historical machine-readable copy: [tasks.json](tasks.json).

The original fixed six-key JSON/immutable `web-games.json` requirements below are superseded: discovery input may be rearranged or removed after verified SQLite import, with a bootstrap asset retained for fresh installs. Follow the current execution plan and architecture, not those historical format restrictions.

## Owner decision (2026-10-24): web-based parent UI

The owner approved re-platforming the parent UI onto a local web stack; the
historical "no web frontend" constraint below is superseded for parent mode
only (child screens stay GTK). Design and security model: architecture.md
section 12b. Remaining rename/rating/Keep-Select and Wi-Fi tasks are
re-targeted as web endpoints/pages on the loopback token-gated server.

Update (2026-10-25): the owner extended the decision to **all UI** — every
screen (child home, Videos, parent mode) is a page on the loopback server
shown in one WebKitGTK view; the Firefox parent browser measured ~921 MB PSS
vs ~225 MB for WebKitGTK on the tablet. See architecture.md §12b and
implementation-status.md; on-device verification of the full port is pending.

## How a junior developer should use this backlog

1. Read the architecture sections referenced by the task and inspect the listed files. Paths for new modules are proposed target paths, not existing implementations.
2. Pick a task only after its dependencies pass; tasks with a failed hardware spike remain blocked.
3. Add the specified tests, implement only that scope, and record the validation commands/results. No actual tablet or root changes without administrator approval.
4. Have the change reviewed before merging. A green fake-backend test does not replace a stated Surface Go acceptance gate.

### Estimation and domains

- Fibonacci sizes: **1** tiny change; **2** bounded configuration/contract; **3** small module/workflow; **5** multi-path integration; **8** hardware/security-heavy spike or acceptance matrix; **13** too large and must be split before assignment. No task here exceeds 8.
- Sizes are relative complexity/uncertainty, **not days**. Re-estimate after the platform spikes; do not convert total points into a delivery date.
- **backend** = local domain/storage/process/network services; **frontend** = GTK screens and user interaction; **other** = audit, tooling, testing, deployment or documentation. No HTTP backend is planned.

**68 tasks; 297 relative points.**

| Domain | Tasks | Points |
|---|---:|---:|
| backend | 27 | 119 |
| frontend | 20 | 93 |
| other | 21 | 85 |

### Definition of done (every task)

- Listed acceptance criteria and tests pass; errors/cancel/cleanup paths are handled, not only the happy path.
- No blocking network/process wait on GTK, secrets in logs, raw catalog commands, silent destructive migrations or scope-expanding privilege grants.
- Domain/services remain testable without GI/display where applicable; new interfaces are typed and injected rather than global.
- State changes use the declared transaction/session ownership rules and remain recoverable.
- Documentation and dependencies reflect any contract change. Hardware evidence is recorded when required; never substitute an assumption for a pass.

### Release gates and useful parallel lanes

- T001 locks product behavior; T002/T003 establish the real platform.
- **T004 is a release-blocking keyboard feasibility gate**. A failed result requires a new keyboard/compositor decision, not disabling WebKit security.
- **T005 is the NM/iwd/permissions gate**. Do not broaden polkit policy to bypass a failed constraint.
- Storage/catalog (T008–T018), process/input (T019–T028), and networking adapters (T041–T047) can develop in parallel once their prerequisite contracts exist.
- UI can use fake services while adapters are completed, but acceptance depends on integrated tasks.
- T065 and T067 gate tablet release. Root/network changes are provisioned by an administrator, not performed automatically by the application.

## Task index

| ID | Task | Size | Domain | Depends on |
|---|---|---:|---|---|
| [T001](#t001) | Confirm product semantics and record the acceptance contract | 2 | other | — |
| [T002](#t002) | Audit the real Surface Go session and hardware | 3 | other | T001 |
| [T003](#t003) | Verify runtime packages and publish the dependency matrix | 3 | other | T002 |
| [T004](#t004) | Prove touch-only portal text entry under Cage | 8 | frontend | T002, T003 |
| [T005](#t005) | Validate libnm with iwd and restricted permissions | 5 | backend | T002, T003 |
| [T006](#t006) | Create test and static-check entry points | 3 | other | T003 |
| [T007](#t007) | Extract the application shell without changing existing tiles | 5 | frontend | T006 |
| [T008](#t008) | Define domain enums, DTOs and validation contracts | 3 | backend | T001, T006 |
| [T009](#t009) | Implement SQLite initialization and versioned migrations | 5 | backend | T008 |
| [T010](#t010) | Add repositories and seed the nine legacy home slots | 5 | backend | T009 |
| [T011](#t011) | Audit discovery records and create provenance exclusions | 3 | other | T001, T008 |
| [T012](#t012) | Generate the canonical flat JSON and schema | 5 | backend | T008, T011 |
| [T013](#t013) | Implement idempotent catalog imports | 5 | backend | T010, T012 |
| [T014](#t014) | Implement status derivation and eligible catalog queries | 3 | backend | T010, T013 |
| [T015](#t015) | Implement home assignment, displacement and movement | 5 | backend | T010, T014 |
| [T016](#t016) | Implement atomic review saves and soft deletion | 5 | backend | T015 |
| [T017](#t017) | Implement the frozen next-game queue | 3 | backend | T014 |
| [T018](#t018) | Add abandoned-session recovery and safe data backups | 5 | backend | T009, T016 |
| [T019](#t019) | Implement the pure three-tap gesture recognizer | 3 | backend | T008 |
| [T020](#t020) | Integrate evdev volume input with the GLib loop | 5 | backend | T002, T019 |
| [T021](#t021) | Handle input hotplug, removal and resume rescan | 3 | backend | T020 |
| [T022](#t022) | Introduce owned launch sessions and persistent outcomes | 5 | backend | T008, T010 |
| [T023](#t023) | Implement isolated Firefox launches and profile cleanup | 5 | backend | T003, T022 |
| [T024](#t024) | Implement route and parent-session controller | 5 | backend | T007, T017, T022 |
| [T025](#t025) | Implement token-safe timeouts and process-group shutdown | 5 | backend | T022, T023 |
| [T026](#t026) | Wire semantic gestures into visible and hidden application states | 5 | frontend | T020, T024, T025 |
| [T027](#t027) | Handle suspend/resume and deadline policy | 3 | backend | T021, T025 |
| [T028](#t028) | Retire the PID watcher and hidden child exit path | 3 | other | T026, T027 |
| [T029](#t029) | Build a reusable nine-position tile grid | 3 | frontend | T007, T010 |
| [T030](#t030) | Implement the parent home screen and Exit | 3 | frontend | T001, T024, T029 |
| [T031](#t031) | Implement catalog rows and status/evidence display | 5 | frontend | T014, T030 |
| [T032](#t032) | Add review filters, search and queue/scroll preservation | 3 | frontend | T017, T031 |
| [T033](#t033) | Implement trial launch feedback and return-to-editor | 5 | frontend | T023, T025, T026, T032 |
| [T034](#t034) | Build the reusable touch keyboard for GTK fields | 5 | frontend | T004, T029 |
| [T035](#t035) | Implement review name, rating and Keep/Select fields | 5 | frontend | T016, T031, T034 |
| [T036](#t036) | Implement the explicit nine-slot selection picker | 5 | frontend | T015, T029, T035 |
| [T037](#t037) | Wire Delete, Ok, and Ok and see next actions | 5 | frontend | T016, T017, T033, T036 |
| [T038](#t038) | Protect unsaved drafts during navigation | 3 | frontend | T024, T035, T037 |
| [T039](#t039) | Render committed game selections on child home | 5 | frontend | T015, T023, T029, T037 |
| [T040](#t040) | Add parent-facing failure and recovery views | 3 | frontend | T018, T033, T038, T039 |
| [T041](#t041) | Define Wi-Fi backend protocol and state machine | 3 | backend | T005, T008 |
| [T042](#t042) | Implement libnm service lifecycle and permissions | 5 | backend | T003, T041 |
| [T043](#t043) | Implement scanning and safe access-point grouping | 5 | backend | T042 |
| [T044](#t044) | Implement the NetworkManager secret agent | 5 | backend | T042 |
| [T045](#t045) | Implement open and personal Wi-Fi connection activation | 5 | backend | T043, T044 |
| [T046](#t046) | Implement cancellation, disconnect, forget and fallback | 5 | backend | T045 |
| [T047](#t047) | Implement connectivity checks and portal signals | 5 | backend | T042, T045 |
| [T048](#t048) | Build the Wi-Fi list, radio and connection-status screen | 5 | frontend | T030, T034, T041, T043, T046, T047 |
| [T049](#t049) | Build credential and hidden-network forms | 5 | frontend | T034, T044, T045, T048 |
| [T050](#t050) | Productionize the WebKit portal keyboard adapter | 5 | frontend | T004, T034 |
| [T051](#t051) | Implement the isolated captive-portal browser view | 5 | frontend | T003, T024, T047, T050 |
| [T052](#t052) | Integrate portal lifecycle, connectivity polling and return gestures | 5 | frontend | T026, T047, T048, T051 |
| [T053](#t053) | Provision least-privilege NetworkManager authorization | 5 | other | T005, T042, T046 |
| [T054](#t054) | Provision iwd backend and connectivity checks with rollback | 5 | other | T002, T005, T047 |
| [T055](#t055) | Add network request recovery and sanitized failure taxonomy | 3 | backend | T046, T047, T052 |
| [T056](#t056) | Complete catalog, review and slot invariant tests | 5 | other | T013, T014, T015, T016, T017, T018 |
| [T057](#t057) | Complete gesture noise/timing and input-adapter tests | 3 | other | T019, T020, T021, T026, T027 |
| [T058](#t058) | Complete process isolation and return-path regression tests | 5 | other | T023, T024, T025, T027, T028, T033, T039 |
| [T059](#t059) | Add NetworkManager D-Bus integration fixtures | 5 | other | T042, T043, T044, T045, T046, T047, T055 |
| [T060](#t060) | Build controlled captive-portal end-to-end fixtures | 5 | other | T050, T051, T052, T059 |
| [T061](#t061) | Add GTK navigation and review workflow smoke tests | 5 | other | T030, T032, T037, T038, T039, T040, T048, T049, T052 |
| [T062](#t062) | Implement structured, privacy-limited diagnostics | 3 | other | T008, T022, T041 |
| [T063](#t063) | Update installation and migrate existing user data safely | 5 | other | T003, T012, T028, T039, T053, T054, T062 |
| [T064](#t064) | Conduct process, browser, input and privilege security review | 5 | other | T023, T028, T050, T051, T053, T054, T062, T063 |
| [T065](#t065) | Execute and record Surface Go hardware acceptance | 8 | other | T004, T005, T056, T057, T058, T059, T060, T061, T063, T064 |
| [T066](#t066) | Write parent usage and administrator operations documentation | 3 | other | T037, T052, T054, T063 |
| [T067](#t067) | Prepare staged rollout, backup and rollback checklist | 3 | other | T018, T063, T065, T066 |
| [T068](#t068) | Add a read-only support and backup utility | 3 | other | T018, T062, T064 |

## Phase A: Platform decisions and feasibility

<a id="t001"></a>
### T001 — Confirm product semantics and record the acceptance contract

- **Size:** 2
- **Domain:** other
- **Dependencies:** None
- **Files/outputs:** `docs/parent-mode/architecture.md`, `docs/parent-mode/decisions.md`

**Implementation steps**

1. Review the assumptions table with the owner, including three labels, Exit behavior, nine slots, video exclusions, soft deletion and unrated versus zero.
2. Record approval or changed defaults, and annotate any tasks whose acceptance criteria change.

**Acceptance criteria**

- All listed ambiguities have an explicit decision; no task relies on the contradictory “2 tiles” wording.
- Document that a hidden gesture is not authentication and that arbitrary web content is not guaranteed child-safe.

**Tests / verification**

- Walk through one keep, select, delete, replacement and queue-end scenario on paper.

<a id="t002"></a>
### T002 — Audit the real Surface Go session and hardware

- **Size:** 3
- **Domain:** other
- **Dependencies:** T001
- **Files/outputs:** `docs/parent-mode/platform-audit.md`

**Implementation steps**

1. Collect installed Python/GI/GTK/Cage/Firefox/NM/iwd versions, current services, DNS/DHCP ownership, session authorization and display scaling using read-only checks.
2. Identify the volume device capabilities/udev identity, suspend behavior, input permissions and compositor protocols. Do not collect normal keyboard input or secrets.
3. Record recovery access and physical-console availability; do not change networking.

**Acceptance criteria**

- The report distinguishes measured target facts from repository assumptions.
- NetworkManager presence, current supplicant and any competing IP manager are explicitly recorded.
- An administrator has a documented recovery route before network migration.

**Tests / verification**

- Reproduce the audit commands as leo; record any permission denials without broadening privileges.

<a id="t003"></a>
### T003 — Verify runtime packages and publish the dependency matrix

- **Size:** 3
- **Domain:** other
- **Dependencies:** T002
- **Files/outputs:** `docs/parent-mode/dependencies.md`, `app/requirements-dev.txt`

**Implementation steps**

1. Map each selected runtime import to Arch packages and test the GIR namespaces Gtk 3.0, NM 1.0 and WebKit2 4.1.
2. Define developer-only pytest/Hypothesis/dbusmock/Ruff/mypy dependencies separately from runtime packages; document supported versions based on the actual tablet.

**Acceptance criteria**

- Every selected runtime library has a package/import smoke check and a recorded version.
- No GTK4, Qt/web frontend, ORM, raw iwd client or pip install into system Python is introduced.

**Tests / verification**

- Run an import/version smoke script in a nonprivileged test environment; make missing optional services report unavailable rather than crash.

<a id="t004"></a>
### T004 — Prove touch-only portal text entry under Cage

- **Size:** 8
- **Domain:** frontend
- **Dependencies:** T002, T003
- **Files/outputs:** `prototypes/portal-keyboard.py`, `docs/parent-mode/portal-keyboard-spike.md`

**Implementation steps**

1. Build a disposable GTK3/WebKit2 4.1 prototype with an ephemeral context, keyboard buttons and the focused-frame editing API. Preserve web-field focus when a key is tapped.
2. Exercise insert, delete, cursor movement and form submit against local text/password forms, UTF-8, redirected HTTPS and a cross-origin iframe. Check can_execute_editing_command rather than assuming commands work.
3. Run on the actual touch display and record behavior. If unreliable, stop and write a compositor/keyboard ADR; do not merge an insecure JS bridge workaround.

**Acceptance criteria**

- The owner can complete the fixture login using touch only, with no external keyboard.
- Typing does not leak into logs or steal focus; password masking remains intact.
- A recorded pass/fail gates T050 and portal release; a failed spike has an explicit redesign decision.

**Tests / verification**

- Manual Surface Go keyboard matrix with screenshots that contain no credentials.
- Verify self-signed TLS is blocked and the prototype never disables browser sandboxing.

<a id="t005"></a>
### T005 — Validate libnm with iwd and restricted permissions

- **Size:** 5
- **Domain:** backend
- **Dependencies:** T002, T003
- **Files/outputs:** `prototypes/nm-smoke.py`, `docs/parent-mode/network-spike.md`

**Implementation steps**

1. On a disposable or locally recoverable setup, test NM.Client discovery, async scan, activation, connectivity states and secret-agent registration.
2. With administrator approval, validate iwd backend configuration and user-restricted profiles; record which polkit actions are actually needed and any credential migration effects.
3. Do not modify the current SSH connection remotely or assume auth_admin dialogs exist in Cage.

**Acceptance criteria**

- The target combination can connect as leo without root-running application code.
- DHCP/DNS ownership, iwd autoconnect policy and restricted-profile remember/forget behavior are recorded.
- Any feature requiring broader privilege is escalated before implementation, not granted silently.

**Tests / verification**

- Connect/reconnect to a disposable WPA2 network and test permission denied.
- Inspect permitted actions/profile restrictions and prove unrelated system profile modification is not newly granted.

<a id="t006"></a>
### T006 — Create test and static-check entry points

- **Size:** 3
- **Domain:** other
- **Dependencies:** T003
- **Files/outputs:** `app/pyproject.toml`, `app/tests/conftest.py`, `docs/parent-mode/development.md`

**Implementation steps**

1. Add pytest configuration, Ruff rules and mypy checks for GI-free modules. Document commands from the project root.
2. Provide fixtures for temporary XDG directories, SQLite files, a fake monotonic clock, fake browser/network adapters and an optional GI display marker.

**Acceptance criteria**

- Pure tests run without GTK display, root access, internet or real Wi-Fi hardware.
- Display/hardware tests are explicitly marked and never accidentally use personal network credentials.

**Tests / verification**

- Run the empty/smoke suite and lint/type commands in a clean developer environment.

## Phase B: Domain, catalog, and persistence

<a id="t007"></a>
### T007 — Extract the application shell without changing existing tiles

- **Size:** 5
- **Domain:** frontend
- **Dependencies:** T006
- **Files/outputs:** `app/launcher.py`, `app/leo_kiosk/application.py`, `app/leo_kiosk/ui/window.py`

**Implementation steps**

1. Move window construction and dependency setup into a package while preserving the current nine tile labels, commands, colors and time limits.
2. Introduce a Gtk.Stack route host and injectable services; keep the entry point small. Do not combine this extraction with catalog changes.

**Acceptance criteria**

- All existing native/local tiles still launch and return through the current behavior during this intermediate refactor.
- The application can be constructed with fake services for UI tests.

**Tests / verification**

- Smoke-test legacy tiles with fake executables and compare the grid configuration before/after extraction.

<a id="t008"></a>
### T008 — Define domain enums, DTOs and validation contracts

- **Size:** 3
- **Domain:** backend
- **Dependencies:** T001, T006
- **Files/outputs:** `app/leo_kiosk/domain/models.py`, `app/tests/unit/test_models.py`

**Implementation steps**

1. Define MediaType (0 other, 1 video, 2 game), review status, selection intent, launch role/outcome, network state and dimension-evidence enums.
2. Create dataclasses/Protocols for catalog items, review drafts, home slots, sessions and Wi-Fi snapshots; validate URL, name, rating and nullable evidence.

**Acceptance criteria**

- No domain module imports GI, subprocess or SQL.
- Zero rating differs from null, unknown orientation differs from portrait, and discovered metadata differs from verified playback.

**Tests / verification**

- Table-driven tests for boundary values, Unicode names, invalid schemes/userinfo/control characters and contradictory dimensions.

<a id="t009"></a>
### T009 — Implement SQLite initialization and versioned migrations

- **Size:** 5
- **Domain:** backend
- **Dependencies:** T008
- **Files/outputs:** `app/leo_kiosk/storage/database.py`, `app/leo_kiosk/storage/migrations/001_initial.sql`

**Implementation steps**

1. Create the schema described in architecture section 6, parameterized connection setup, UTC timestamps and migration tracking. Enable foreign keys/WAL and a finite busy timeout.
2. Resolve XDG paths, create private directories, take a SQLite API backup before upgrades and fail with a typed error rather than replacing bad data.

**Acceptance criteria**

- Fresh creation and repeated startup are idempotent; migrations are transactional.
- Database constraints reject duplicate game identities, invalid ratings/positions and mixed game/legacy slot content.
- Upgrade failure leaves a usable backup and no silently empty database.

**Tests / verification**

- Fresh/migrated/corrupt/read-only/disk-error fixture cases; foreign-key and rollback assertions.

<a id="t010"></a>
### T010 — Add repositories and seed the nine legacy home slots

- **Size:** 5
- **Domain:** backend
- **Dependencies:** T009
- **Files/outputs:** `app/leo_kiosk/storage/repositories.py`, `app/leo_kiosk/services/home.py`

**Implementation steps**

1. Implement catalog/query, home-slot and launch-history repositories with parameterized SQL and DTO returns.
2. Seed all nine existing tiles from tiles.json exactly once, preserving trusted argv/time limits; never let catalog input create native commands.
3. Keep database writes on the owning thread and transactions explicit.

**Acceptance criteria**

- There are exactly nine stable slot rows after first and subsequent starts.
- Reinitialization does not overwrite a parent-selected game or remove an existing native activity.

**Tests / verification**

- Seed twice, update one slot, seed again and assert the update remains; reject malformed trusted config without partial seeding.

<a id="t011"></a>
### T011 — Audit discovery records and create provenance exclusions

- **Size:** 3
- **Domain:** other
- **Dependencies:** T001, T008
- **Files/outputs:** `web-games.json`, `catalog/provenance.json`, `docs/parent-mode/catalog-audit.md`

**Implementation steps**

1. Preserve the existing web-games.json snapshot and record its checksum. Enumerate source records with stable IDs.
2. Classify known hub/section entries, videos, unknown names and dimension claims; mark Gulli popup sizes and inferred Lumni sizes as unverified game resolutions.
3. Record exclusions with reasons rather than deleting original evidence or asserting all HTTP-200 entries are playable.

**Acceptance criteria**

- The original 109 records are accounted for in a reproducible audit.
- Known generic section links are excluded from playable game review; videos are separately classified.
- No exact final playable count is invented before the audit.

**Tests / verification**

- Check record reconciliation against the original checksum and spot-review the known Starfall/Sesame hub entries.

<a id="t012"></a>
### T012 — Generate the canonical flat JSON and schema

- **Size:** 5
- **Domain:** backend
- **Dependencies:** T008, T011
- **Files/outputs:** `tools/normalize_catalog.py`, `catalog/games.json`, `catalog/games.schema.json`, `catalog/provenance.json`

**Implementation steps**

1. Implement an offline converter from grouped web-games.json to the exact six-key flat schema and validate it with jsonschema Draft 2020-12.
2. Use stable UUIDv5 identity in the sidecar, type mapping 0/1/2, 0/0 unknown size and orientation_known metadata; preserve source query strings/fragments.
3. Make output deterministic and report rejected/excluded entries with source indices.

**Acceptance criteria**

- The normalized catalog is an actual committed JSON file; no parent decisions are stored in it.
- Every schema-compatible unknown value has a matching provenance explanation; inferred dimensions are not upgraded to measured facts.
- Re-running produces byte-identical generated files for unchanged inputs.

**Tests / verification**

- Fixture conversion tests for each provider shape, wrong type, duplicates, malformed URLs, null dimensions and unknown orientation.

<a id="t013"></a>
### T013 — Implement idempotent catalog imports

- **Size:** 5
- **Domain:** backend
- **Dependencies:** T010, T012
- **Files/outputs:** `app/leo_kiosk/services/catalog.py`, `app/tests/integration/test_catalog_import.py`

**Implementation steps**

1. Validate an entire normalized source/manifest before opening the import transaction; emit added/updated/unchanged/excluded/error counts and checksum.
2. Upsert source metadata by stable identity without overwriting parent fields/history, selection, tombstones or locally retained removed-source items.
3. Avoid network fetches during startup/import; surface actionable validation errors.

**Acceptance criteria**

- Malformed files leave the previous catalog unchanged.
- Reimport cannot resurrect deletions or reset reviews/slots; repeated import is idempotent.

**Tests / verification**

- Import, review/select/delete, reimport updated metadata and assert all parent decisions survive; simulate a mid-transaction error.

<a id="t014"></a>
### T014 — Implement status derivation and eligible catalog queries

- **Size:** 3
- **Domain:** backend
- **Dependencies:** T010, T013
- **Files/outputs:** `app/leo_kiosk/services/catalog.py`, `app/leo_kiosk/storage/repositories.py`

**Implementation steps**

1. Derive selected/reviewed/tested/new in the documented precedence; keep deleted and launch failures as separate dimensions.
2. Provide deterministic search/filter/order queries with primary game-only eligibility and separate optional video discovery view.

**Acceptance criteria**

- Selected is derived from slots, never an independent flag.
- Re-testing a selected/reviewed game does not downgrade it; blocked/failed trials do not imply successful playback.

**Tests / verification**

- Status truth table, tombstone filtering and stable tie-break ordering tests.

<a id="t015"></a>
### T015 — Implement home assignment, displacement and movement

- **Size:** 5
- **Domain:** backend
- **Dependencies:** T010, T014
- **Files/outputs:** `app/leo_kiosk/services/home.py`, `app/tests/unit/test_home_assignments.py`

**Implementation steps**

1. Expose transactional choose/replace/move/unselect operations over positions 1–9 and reject unreviewed/deleted/nongame entries.
2. Require explicit replacement intent and preserve displaced games as reviewed; leaving a source slot empty after a move is intentional.
3. Prevent slot deletion and verify uniqueness at repository/domain boundaries.

**Acceptance criteria**

- No tenth selected game or duplicate placement can be committed.
- Legacy activities are replaced only with explicit consent, not merely when the catalog imports.

**Tests / verification**

- Fill nine slots, replace/move/unselect/delete, attempt invalid direct writes and assert invariant preservation after failures.

<a id="t016"></a>
### T016 — Implement atomic review saves and soft deletion

- **Size:** 5
- **Domain:** backend
- **Dependencies:** T015
- **Files/outputs:** `app/leo_kiosk/services/reviews.py`, `app/tests/integration/test_review_transactions.py`

**Implementation steps**

1. Implement save_review with expected revision, name/rating validation, Keep/Select intent and optional slot operation in one transaction.
2. Implement delete_game with unselection/tombstone/audit event in one transaction; do not apply unsaved draft fields during deletion.
3. Return typed conflict/storage/validation errors so the UI retains draft values.

**Acceptance criteria**

- Successful Ok marks reviewed, while failed save changes neither metadata nor home assignments.
- Deleting a selected game removes its tile and leaves the other eight positions stable.

**Tests / verification**

- Test 0/100/null ratings, stale revision, replacement rollback, disk failure and delete/reimport behavior.

<a id="t017"></a>
### T017 — Implement the frozen next-game queue

- **Size:** 3
- **Domain:** backend
- **Dependencies:** T014
- **Files/outputs:** `app/leo_kiosk/domain/review_queue.py`, `app/tests/unit/test_review_queue.py`

**Implementation steps**

1. Snapshot the displayed eligible IDs on trial activation and store current index separately from search/sort widgets.
2. Compute the next eligible ID while skipping deleted/excluded entries, without wrapping or inserting newly imported entries.

**Acceptance criteria**

- Rename/rating/filter/import changes cannot reorder the active review sequence.
- Queue end is explicit and cannot accidentally relaunch the first game.

**Tests / verification**

- Queue tests for single item, deleted next item, no eligible remainder and renamed items whose sort position changes.

<a id="t018"></a>
### T018 — Add abandoned-session recovery and safe data backups

- **Size:** 5
- **Domain:** backend
- **Dependencies:** T009, T016
- **Files/outputs:** `app/leo_kiosk/services/recovery.py`, `app/leo_kiosk/storage/repositories.py`

**Implementation steps**

1. On startup mark unfinished historical launch rows abandoned and offer recovery of the most recent review trial; do not signal stored PIDs.
2. Provide a safe SQLite backup/export operation with schema/catalog checksum metadata and instructions to restore only when the app is stopped.
3. Keep corrupt-data behavior non-destructive and identify errors for the parent without resetting selections.

**Acceptance criteria**

- Committed reviews/slots survive simulated power loss and launch interruption.
- A stale PID file cannot cause another process to be killed after reboot.

**Tests / verification**

- Restart recovery fixtures, SQLite backup round-trip and failed-backup tests preserving the original database.

## Phase C: Input, navigation, and process ownership

<a id="t019"></a>
### T019 — Implement the pure three-tap gesture recognizer

- **Size:** 3
- **Domain:** backend
- **Dependencies:** T008
- **Files/outputs:** `app/leo_kiosk/domain/gestures.py`, `app/tests/unit/test_gestures.py`

**Implementation steps**

1. Implement Up/Down/Down and Down/Down/Up with rolling suffix handling, configurable gap/total window and consumed-sequence cooldown.
2. Expose explicit reset(reason) and inject a monotonic clock; ignore releases/repeats/unrelated events before state mutation.

**Acceptance criteria**

- Each valid sequence emits exactly one semantic action and old Down/Up emits none.
- Timing boundaries, invalid prefixes and route resets have defined behavior.

**Tests / verification**

- Exact patterns, overlaps, timeout, fast intentional taps, repeat/release noise and cooldown boundary tests.

<a id="t020"></a>
### T020 — Integrate evdev volume input with the GLib loop

- **Size:** 5
- **Domain:** backend
- **Dependencies:** T002, T019
- **Files/outputs:** `app/leo_kiosk/adapters/input.py`

**Implementation steps**

1. Enumerate evdev capabilities and open only configured devices exposing volume keys, using measured stable identity where available.
2. Attach nonblocking device fds to GLib watches; convert only accepted volume key-down events to recognizer input and expose an input-unavailable diagnostic.
3. Do not grab events, log general keyboard input or require a displayed GTK window.

**Acceptance criteria**

- Gestures work while the launcher is hidden behind an external app.
- Missing permission/device does not crash the launcher; input cleanup closes watches/fds exactly once.

**Tests / verification**

- Fake evdev fd tests for short batches, unrelated events, read errors, teardown and duplicate physical sources.

<a id="t021"></a>
### T021 — Handle input hotplug, removal and resume rescan

- **Size:** 3
- **Domain:** backend
- **Dependencies:** T020
- **Files/outputs:** `app/leo_kiosk/adapters/input.py`

**Implementation steps**

1. Attach pyudev input-device monitoring to GLib and reuse the same capability/identity filter on additions.
2. Remove dead watches/fds, reset partial gestures on removal and expose a rescan operation for resume.

**Acceptance criteria**

- A re-added volume device starts working without launcher restart.
- Duplicate add/remove notifications do not duplicate actions or leak descriptors.

**Tests / verification**

- Simulate disconnect/reconnect, duplicate events and a device that becomes readable only after a permission change.

<a id="t022"></a>
### T022 — Introduce owned launch sessions and persistent outcomes

- **Size:** 5
- **Domain:** backend
- **Dependencies:** T008, T010
- **Files/outputs:** `app/leo_kiosk/services/sessions.py`, `app/leo_kiosk/adapters/legacy_apps.py`

**Implementation steps**

1. Replace unstructured self.proc state with a tokenized session object, launch role, return context, captured process group and explicit lifecycle phases.
2. Keep legacy command execution restricted to trusted configuration and persist launch attempt/outcome records.
3. Guard launch requests so only one external activity can start at a time.

**Acceptance criteria**

- Repeated tile taps cannot start concurrent sessions.
- Spawn failure preserves the current UI and does not mark a new game tested.

**Tests / verification**

- Fake-process tests for successful launch, unavailable executable, duplicate launch and correctly recorded role/game ID.

<a id="t023"></a>
### T023 — Implement isolated Firefox launches and profile cleanup

- **Size:** 5
- **Domain:** backend
- **Dependencies:** T003, T022
- **Files/outputs:** `app/leo_kiosk/adapters/firefox.py`, `app/tests/integration/test_firefox_adapter.py`

**Implementation steps**

1. Build validated argument arrays for kiosk/no-remote/new-instance/profile modes; choose native Wayland environment settings compatible with the installed version.
2. Create separate ephemeral review profiles and a persistent child-only profile, with private filesystem permissions and cleanup after complete shutdown.
3. Apply reviewed Firefox policies/preferences for downloads, external handlers and prompts without disabling sandbox/TLS or breaking required game storage.

**Acceptance criteria**

- An already-running administrator/default Firefox cannot capture a game launch.
- Catalog data cannot supply executable argv; portal cookies never share the game profile.
- Profile-lock and startup failures are typed and recoverable.

**Tests / verification**

- Command/profile unit tests and a controlled Firefox process test using a local HTML game fixture.

<a id="t024"></a>
### T024 — Implement route and parent-session controller

- **Size:** 5
- **Domain:** backend
- **Dependencies:** T007, T017, T022
- **Files/outputs:** `app/leo_kiosk/services/navigation.py`

**Implementation steps**

1. Represent all routes and their payloads explicitly; implement the architecture gesture/context transition table.
2. Track the parent-session flag, review return game/queue, filters and pending launch transitions outside widgets.
3. Require UI confirmation callbacks when navigation would discard a dirty review editor.

**Acceptance criteria**

- Trial return always identifies the exact game and child exit always returns home.
- Exit ends parent mode only; no navigation action quits Cage or invokes a shell.

**Tests / verification**

- Table-driven route transition tests, dirty-editor cancel/discard/save and superseded navigation requests.

<a id="t025"></a>
### T025 — Implement token-safe timeouts and process-group shutdown

- **Size:** 5
- **Domain:** backend
- **Dependencies:** T022, T023
- **Files/outputs:** `app/leo_kiosk/services/sessions.py`

**Implementation steps**

1. Add nonblocking process observation, deadlines, TERM then bounded KILL escalation and owned-group cleanup.
2. Capture session tokens/processes in every callback, cancel timer sources on completion and make stop idempotent across gesture/crash/timeout races.
3. Return one final outcome and leave no unowned .app-pid kill path.

**Acceptance criteria**

- A stale callback cannot terminate or navigate away from a newer session.
- Every completion path restores navigation and accounts for process-group descendants.

**Tests / verification**

- Controlled subprocess tests with ignored TERM and child processes; race duplicate exit/timeout/gesture callbacks and verify one completion.

<a id="t026"></a>
### T026 — Wire semantic gestures into visible and hidden application states

- **Size:** 5
- **Domain:** frontend
- **Dependencies:** T020, T024, T025
- **Files/outputs:** `app/leo_kiosk/application.py`, `app/leo_kiosk/ui/window.py`

**Implementation steps**

1. Connect InputMonitor actions to the controller, stopping owned playback before showing the target parent/child/review route.
2. Reset recognizer state on every route transition and present/focus the existing GTK window without opening duplicate windows.
3. Display an actionable parent diagnostic when physical buttons are unavailable.

**Acceptance criteria**

- Both sequences work with GTK hidden, Firefox focused and parent forms active.
- The documented route matrix is matched without accidental old-shortcut activation.

**Tests / verification**

- Controller/UI integration with fake gestures plus manual focused-Firefox check under Cage.

<a id="t027"></a>
### T027 — Handle suspend/resume and deadline policy

- **Size:** 3
- **Domain:** backend
- **Dependencies:** T021, T025
- **Files/outputs:** `app/leo_kiosk/services/sessions.py`, `app/leo_kiosk/application.py`

**Implementation steps**

1. Subscribe to logind sleep/resume notifications through Gio and reset gesture state/rescan input/refresh networking on wake.
2. Use Linux CLOCK_BOOTTIME for child and parent-trial deadlines so sleep counts and wall-clock corrections do not change the limit. Recheck on wake; persist UTC history only and recover rebooted sessions as abandoned.

**Acceptance criteria**

- A session cannot gain indefinite extra time by suspending the tablet.
- Resume does not trigger a gesture from stale partial input or crash on removed devices.

**Tests / verification**

- Fake clock/logind tests for suspend past expiry, clock shift and reconnect; one hardware sleep/wake trial.

<a id="t028"></a>
### T028 — Retire the PID watcher and hidden child exit path

- **Size:** 3
- **Domain:** other
- **Dependencies:** T026, T027
- **Files/outputs:** `app/run.sh`, `app/backwatch.py`, `app/launcher.py`, `README.md`

**Implementation steps**

1. Stop launching backwatch.py, remove .app-pid production signaling and remove the five-tap child-accessible kiosk exit corner.
2. Ensure launcher shutdown closes input/browser resources; keep the main process foregrounded so Cage lifecycle is unchanged.
3. Document the changed gestures and administrator recovery rather than keeping conflicting shortcuts.

**Acceptance criteria**

- Exactly one process interprets volume input; no orphaned watcher remains after logout.
- Child/home gestures never expose a console, and old watcher/PID state is safely ignored.

**Tests / verification**

- Inspect process tree after boot/exit/restart and prove no hidden-corner exit remains in UI smoke tests.

## Phase D: Parent and review interface

<a id="t029"></a>
### T029 — Build a reusable nine-position tile grid

- **Size:** 3
- **Domain:** frontend
- **Dependencies:** T007, T010
- **Files/outputs:** `app/leo_kiosk/ui/tile_grid.py`, `app/leo_kiosk/ui/styles.css`

**Implementation steps**

1. Extract shared three-by-three geometry with homogeneous expansion, margins, spacing and large touch targets.
2. Provide parent grey/disabled and child colored render models without sharing action handlers; handle long labels at tablet scale.

**Acceptance criteria**

- Both screens always render nine positions with matching geometry.
- Disabled tiles are not clickable or focusable; labels remain readable without changing hit areas.

**Tests / verification**

- Widget-model tests and landscape/portrait/small-display screenshots.

<a id="t030"></a>
### T030 — Implement the parent home screen and Exit

- **Size:** 3
- **Domain:** frontend
- **Dependencies:** T001, T024, T029
- **Files/outputs:** `app/leo_kiosk/ui/parent_home.py`

**Implementation steps**

1. Render grey Review/Wifi/Exit tiles followed by six blank disabled grey tiles and a Parent title.
2. Route Review and Wifi through the controller; Exit clears the parent session and shows child home.

**Acceptance criteria**

- Only three parent tiles have labels/actions.
- Exit never quits the GTK main loop or the compositor.

**Tests / verification**

- UI assertions for nine tiles, exact labels, disabled placeholders and Exit navigation.

<a id="t031"></a>
### T031 — Implement catalog rows and status/evidence display

- **Size:** 5
- **Domain:** frontend
- **Dependencies:** T014, T030
- **Files/outputs:** `app/leo_kiosk/ui/review_list.py`

**Implementation steps**

1. Build a touch-scrollable list with name, status badge, provider, optional rating and sanitized last-trial evidence.
2. Bind rows by stable game ID, show selected-game and occupied-slot counts separately, and provide empty/error states.
3. Offer an explicit Edit review secondary action without treating row selection as approval.

**Acceptance criteria**

- All four requested statuses are visible as text and correct after repository changes.
- Names/URLs are rendered as plain text and unknown evidence is labeled Unknown, not portrait or measured.

**Tests / verification**

- Render representative DTOs including long Unicode names, rating zero, no rating, blocked game and empty results.

<a id="t032"></a>
### T032 — Add review filters, search and queue/scroll preservation

- **Size:** 3
- **Domain:** frontend
- **Dependencies:** T017, T031
- **Files/outputs:** `app/leo_kiosk/ui/review_list.py`

**Implementation steps**

1. Add status/provider/search controls and default game-only eligibility, with optional separate video discovery filtering but no video launch feature.
2. Preserve filter state/scroll anchor when leaving and snapshot the eligible displayed queue at trial activation.

**Acceptance criteria**

- Returning from a trial/editor restores the expected row and filter.
- Next-game order is unaffected by later edits/imports, and unsupported videos are not selectable into game slots.

**Tests / verification**

- List/controller tests for filtered queues, renamed items, deleted scroll anchor and empty filtered results.

<a id="t033"></a>
### T033 — Implement trial launch feedback and return-to-editor

- **Size:** 5
- **Domain:** frontend
- **Dependencies:** T023, T025, T026, T032
- **Files/outputs:** `app/leo_kiosk/ui/review_list.py`, `app/leo_kiosk/services/reviews.py`

**Implementation steps**

1. On row activation show loading/return-gesture guidance, launch the exact game URL and mark tested only after successful spawn.
2. On gesture, natural exit, timeout or crash open that game editor with the captured outcome/queue; keep errors distinct from playback verification.

**Acceptance criteria**

- Rapid double tap starts one trial; failed spawn does not hide the list or lose selection.
- Down/Down/Up and crash return to the editor, never the child home by accident.

**Tests / verification**

- Integration scenarios for working, spawn-failing, immediately exiting and timed-out trial fixtures.

<a id="t034"></a>
### T034 — Build the reusable touch keyboard for GTK fields

- **Size:** 5
- **Domain:** frontend
- **Dependencies:** T004, T029
- **Files/outputs:** `app/leo_kiosk/ui/keyboard.py`

**Implementation steps**

1. Implement Gtk.Editable-targeted insert/delete/cursor actions, layouts for names/passwords and numeric entry, and an explicit show/hide control.
2. Keep keyboard buttons from becoming the editing target, handle UTF-8 selections, and resize/pan forms so active fields and bottom CTAs remain reachable.
3. Do not echo password characters into auxiliary labels/logs or write keyboard history.

**Acceptance criteria**

- Parent can rename and enter a Wi-Fi password using touch only.
- Keyboard opening/closing preserves draft values and the correct editing target.

**Tests / verification**

- GTK tests for Unicode, selections, masked text, focus change and action-bar visibility at tablet resolution.

<a id="t035"></a>
### T035 — Implement review name, rating and Keep/Select fields

- **Size:** 5
- **Domain:** frontend
- **Dependencies:** T016, T031, T034
- **Files/outputs:** `app/leo_kiosk/ui/review_editor.py`

**Implementation steps**

1. Render original/display names, editable 1–80 character name, optional rating with slider/numeric +/- controls and Keep/Select draft choice.
2. Initialize previously selected games with their current selection, validate before save and show field-level errors without mutating the database.

**Acceptance criteria**

- Null, zero and 100 percent round-trip correctly; invalid edits cannot be committed.
- Editor shows original URL/provider/status/trial outcome and evidence without implying success.

**Tests / verification**

- Widget/domain tests for boundaries, whitespace, very long Unicode names and selected-item defaults.

<a id="t036"></a>
### T036 — Implement the explicit nine-slot selection picker

- **Size:** 5
- **Domain:** frontend
- **Dependencies:** T015, T029, T035
- **Files/outputs:** `app/leo_kiosk/ui/slot_picker.py`, `app/leo_kiosk/ui/review_editor.py`

**Implementation steps**

1. Show nine numbered positions with current native/game occupant names and the current assignment when present.
2. Require slot choice for new selections and confirmation naming the displaced item; represent move versus replacement clearly.
3. Keep choices as draft intent until the final save transaction commits.

**Acceptance criteria**

- Choosing/canceling a slot does not alter child home prematurely.
- Full home capacity cannot cause automatic eviction or a hidden tenth selection.

**Tests / verification**

- UI/service tests for empty slot, legacy replacement, selected replacement, movement and cancel.

<a id="t037"></a>
### T037 — Wire Delete, Ok, and Ok and see next actions

- **Size:** 5
- **Domain:** frontend
- **Dependencies:** T016, T017, T033, T036
- **Files/outputs:** `app/leo_kiosk/ui/review_editor.py`

**Implementation steps**

1. Add a fixed bottom action bar; Delete confirms tombstone/unselection, Ok saves and returns to list, Next saves then launches the frozen next ID.
2. Disable repeat submission while saving; on failure keep all draft values and do not advance.
3. At queue end show a completion message without wrapping; deletion returns to the nearest remaining list row.

**Acceptance criteria**

- All three CTAs have exactly the documented transaction/navigation behavior.
- No save failure or canceled confirmation loses edits, changes slots or launches next.

**Tests / verification**

- End-to-end fake-adapter tests for each CTA, last item, failed save, failed next launch and selected deletion.

<a id="t038"></a>
### T038 — Protect unsaved drafts during navigation

- **Size:** 3
- **Domain:** frontend
- **Dependencies:** T024, T035, T037
- **Files/outputs:** `app/leo_kiosk/ui/review_editor.py`, `app/leo_kiosk/services/navigation.py`

**Implementation steps**

1. Track dirty drafts separately from persisted trial state and intercept back, parent gesture and page changes.
2. Implement Save/Discard/Cancel confirmation; Discard changes only the draft, while Cancel preserves route, focus and keyboard state.

**Acceptance criteria**

- An accidental gesture cannot silently approve a game or discard edited name/rating.
- Clean editors navigate without an unnecessary confirmation.

**Tests / verification**

- Dirty/clean navigation matrix including failed Save and Cancel while keyboard is open.

<a id="t039"></a>
### T039 — Render committed game selections on child home

- **Size:** 5
- **Domain:** frontend
- **Dependencies:** T015, T023, T029, T037
- **Files/outputs:** `app/leo_kiosk/ui/child_home.py`, `app/leo_kiosk/services/home.py`

**Implementation steps**

1. Render all nine persisted slots, preserving native activity styles/commands and displaying selected games with parent names and deterministic colors.
2. Launch game slots with the child profile and per-slot/default time limit; make empty tiles disabled.
3. Refresh from committed data after exiting parent mode or replacing/deleting a selected item.

**Acceptance criteria**

- Reboot and parent Exit show exactly the committed slot layout, including native activities not replaced.
- Game playback returns to child home and retains only child profile data.

**Tests / verification**

- Home rendering/launch tests covering mixed legacy/game/empty slots, rename, replacement and deletion.

<a id="t040"></a>
### T040 — Add parent-facing failure and recovery views

- **Size:** 3
- **Domain:** frontend
- **Dependencies:** T018, T033, T038, T039
- **Files/outputs:** `app/leo_kiosk/ui/diagnostics.py`

**Implementation steps**

1. Render typed catalog/database/browser/input errors with Retry/Back and safe recovery choices, without resetting state.
2. Offer recovered review after interrupted trials and preserve navigation/filter context after transient failures.

**Acceptance criteria**

- Permission/disk/corrupt-data failures never look like a successful empty catalog.
- No error banner exposes traceback secrets or raw untrusted markup.

**Tests / verification**

- Fault-injection UI tests for read-only DB, profile lock, missing browser/input and abandoned review session.

## Phase E: Wi-Fi and captive portals

<a id="t041"></a>
### T041 — Define Wi-Fi backend protocol and state machine

- **Size:** 3
- **Domain:** backend
- **Dependencies:** T005, T008
- **Files/outputs:** `app/leo_kiosk/services/wifi.py`, `app/tests/unit/test_wifi_state.py`

**Implementation steps**

1. Define device/AP/connection snapshots, radio/connectivity enums, request generations and cancellable backend operations.
2. Model scan/connect/check/portal/online/error states and make screen navigation independent from raw NM objects.

**Acceptance criteria**

- Frontends can be tested with a fake adapter and no system D-Bus.
- Late completion for an older network/request cannot overwrite current state.

**Tests / verification**

- State transition tests including radio-off, unsupported security, portal, unknown check availability and request supersession.

<a id="t042"></a>
### T042 — Implement libnm service lifecycle and permissions

- **Size:** 5
- **Domain:** backend
- **Dependencies:** T003, T041
- **Files/outputs:** `app/leo_kiosk/adapters/networkmanager.py`

**Implementation steps**

1. Construct NM.Client, subscribe to service/device/radio/permission changes and translate them into immutable snapshots.
2. Detect service absence/restart and hardware rfkill; reconnect signal handlers without leaking callbacks.
3. Report permissions explicitly rather than relying on an authentication dialog in Cage.

**Acceptance criteria**

- NM restart/device removal does not crash GTK or leave stale selectable devices.
- Denied operations are disabled/explained before mutation where possible.

**Tests / verification**

- Mock service disappearance/reappearance, permission changes and multiple Wi-Fi devices.

<a id="t043"></a>
### T043 — Implement scanning and safe access-point grouping

- **Size:** 5
- **Domain:** backend
- **Dependencies:** T042
- **Files/outputs:** `app/leo_kiosk/adapters/networkmanager.py`

**Implementation steps**

1. Use async request_scan and AP change signals with rate limiting and one outstanding scan per device.
2. Group by SSID bytes plus compatible security family, preserve strongest/current/saved indicators and sanitize display names.

**Acceptance criteria**

- Open and protected networks with the same text SSID are never merged into one connection choice.
- Throttled scans and missing SSIDs produce meaningful states without blocking the UI.

**Tests / verification**

- Mock duplicate APs, non-UTF8 SSIDs, strongest-AP changes, throttling and lost device during scan.

<a id="t044"></a>
### T044 — Implement the NetworkManager secret agent

- **Size:** 5
- **Domain:** backend
- **Dependencies:** T042
- **Files/outputs:** `app/leo_kiosk/adapters/secret_agent.py`

**Implementation steps**

1. Subclass/register NM.SecretAgentOld and map GetSecrets/CancelGetSecrets/save/delete callbacks to bounded parent credential requests.
2. Scope responses to the currently authorized connection request, clear pending prompts on cancel/service loss and unregister on shutdown.
3. Keep credentials out of logs/argv/SQLite; describe remember versus transient storage honestly.

**Acceptance criteria**

- A secret request can be canceled or rejected without hanging NM.
- Unrelated/obsolete connection requests cannot retrieve credentials from a previous form.

**Tests / verification**

- Mock agent registration, wrong-password retry, cancel-after-form-entry, daemon restart and denied unrelated connection.

<a id="t045"></a>
### T045 — Implement open and personal Wi-Fi connection activation

- **Size:** 5
- **Domain:** backend
- **Dependencies:** T043, T044
- **Files/outputs:** `app/leo_kiosk/adapters/networkmanager.py`, `app/leo_kiosk/services/wifi.py`

**Implementation steps**

1. Activate compatible saved connections or create validated user-restricted profiles for open/WPA2/supported WPA3 and hidden personal networks.
2. Apply remember/transient policy validated in T005; wait for actual device/active-connection outcomes rather than treating the method return as internet success.
3. Reject unsupported enterprise/security with an actionable administrator message.

**Acceptance criteria**

- Open networks require explicit consent and saved security cannot silently downgrade.
- Credentials are not passed to a shell; persistent profiles use validated restrictions and protected stores only.

**Tests / verification**

- Mock open/WPA2/WPA3 capability/hidden network, wrong password, DHCP failure and unsupported 802.1X cases.

<a id="t046"></a>
### T046 — Implement cancellation, disconnect, forget and fallback

- **Size:** 5
- **Domain:** backend
- **Dependencies:** T045
- **Files/outputs:** `app/leo_kiosk/services/wifi.py`, `app/leo_kiosk/adapters/networkmanager.py`

**Implementation steps**

1. Track ownership of newly requested activations so Cancel can deactivate only that pending attempt.
2. Implement explicit disconnect/forget of authorized user profiles and prevent deleting administrator/system-wide profiles.
3. Remember the prior active profile and offer a bounded reconnect action after a failed switch; do not retry in an infinite loop.

**Acceptance criteria**

- Late cancellation cannot disconnect a newer or unrelated successful connection.
- Forget never broadens profile permissions or deletes a system connection via a privileged fallback.

**Tests / verification**

- Race connect A/connect B/cancel A, service loss, restricted forget and failed-switch reconnect tests.

<a id="t047"></a>
### T047 — Implement connectivity checks and portal signals

- **Size:** 5
- **Domain:** backend
- **Dependencies:** T042, T045
- **Files/outputs:** `app/leo_kiosk/services/wifi.py`, `app/leo_kiosk/adapters/networkmanager.py`

**Implementation steps**

1. Expose configured check availability/URI and NM unknown/none/limited/portal/full distinctly.
2. Use bounded async rechecks with one outstanding request and generation checks; stop timers when leaving/changing network.
3. Offer manual login for unknown/limited/disabled checks without inventing an Online result.

**Acceptance criteria**

- Association success is never equated to internet access.
- Disabled probes and unreachable endpoints remain explicit uncertainty states, not automatic disconnection.

**Tests / verification**

- Mock transitions portal-to-full, limited/unknown, canceled checks, disabled configuration and network change during check.

<a id="t048"></a>
### T048 — Build the Wi-Fi list, radio and connection-status screen

- **Size:** 5
- **Domain:** frontend
- **Dependencies:** T030, T034, T041, T043, T046, T047
- **Files/outputs:** `app/leo_kiosk/ui/wifi.py`

**Implementation steps**

1. Show radio state, accessible AP rows, signal/security/saved/active text, Scan and connection/disconnect/forget controls.
2. Bind to snapshots and use loading/disabled/error states; keep a visible return path and Sign in/Open login actions.
3. Do not offer unauthorized or unsupported actions as if they will work.

**Acceptance criteria**

- Parent can scan/select/inspect connection state with touch only; no terminal/tool parsing is exposed.
- State and request errors stay comprehensible across NM restart or AP disappearance.

**Tests / verification**

- Fake-backend UI cases for empty scan, blocked radio, connecting, wrong password, portal, online and denied permissions.

<a id="t049"></a>
### T049 — Build credential and hidden-network forms

- **Size:** 5
- **Domain:** frontend
- **Dependencies:** T034, T044, T045, T048
- **Files/outputs:** `app/leo_kiosk/ui/wifi_credentials.py`

**Implementation steps**

1. Provide masked password entry/show toggle, Remember choice, hidden SSID/security form and open-network warning.
2. Validate supported credential formats before submission, clear buffers on cancel/finish and show retry errors without logging values.
3. Route secret-agent prompts to the matching active form and ignore obsolete prompts.

**Acceptance criteria**

- All forms are usable with the GTK keyboard and bottom controls remain reachable.
- No credentials are written to catalog/review exports or reused for another SSID request.

**Tests / verification**

- Boundary/password-form tests, Cancel, wrong-password retry, hidden SSID bytes/display and interrupted secret request.

<a id="t050"></a>
### T050 — Productionize the WebKit portal keyboard adapter

- **Size:** 5
- **Domain:** frontend
- **Dependencies:** T004, T034
- **Files/outputs:** `app/leo_kiosk/ui/keyboard.py`, `app/leo_kiosk/ui/portal.py`

**Implementation steps**

1. Convert the successful prototype into a separate focused-webview input target using supported editing commands and capability checks.
2. Keep non-focus-stealing keys, show/hide behavior, UTF-8/password handling and submit controls within the parent UI.
3. Document unsupported target fields and block release if the measured prototype gate is no longer satisfied.

**Acceptance criteria**

- The production component reproduces touch-only login behavior under Cage.
- It introduces no privileged JavaScript bridge, TLS bypass or disabled sandbox.

**Tests / verification**

- Reuse the prototype keyboard matrix against production widgets, including cross-origin iframe input and focus after redirect.

<a id="t051"></a>
### T051 — Implement the isolated captive-portal browser view

- **Size:** 5
- **Domain:** frontend
- **Dependencies:** T003, T024, T047, T050
- **Files/outputs:** `app/leo_kiosk/ui/portal.py`

**Implementation steps**

1. Create a fresh ephemeral WebKit context per connection workflow and load the administrator-configured HTTP entrypoint on explicit parent action.
2. Add host display, Back/Reload/keyboard/Check/Done/Cancel; contain necessary popups in the same isolated context.
3. Reject downloads/custom schemes/external applications/privileged permission requests and retain default TLS failure behavior.

**Acceptance criteria**

- Parent login state never shares child or review Firefox profiles.
- HTTP-to-HTTPS login redirects work while unsafe navigation and certificate bypass remain blocked.

**Tests / verification**

- Local fixture tests for redirect, popup, download, custom scheme, self-signed certificate and host-label sanitization.

<a id="t052"></a>
### T052 — Integrate portal lifecycle, connectivity polling and return gestures

- **Size:** 5
- **Domain:** frontend
- **Dependencies:** T026, T047, T048, T051
- **Files/outputs:** `app/leo_kiosk/ui/portal.py`, `app/leo_kiosk/services/wifi.py`

**Implementation steps**

1. Poll connectivity modestly while open, never reload/submit the form automatically, and show success with explicit Done.
2. Close/cancel/destroy context and timers on network change, parent exit or return gesture; return to Wifi without falsely declaring Online.
3. Support disabled checks/manual login and preserve useful failure/retry states.

**Acceptance criteria**

- Down/Down/Up exits only the portal workflow to Wifi; Up/Down/Down returns to parent home.
- A stale successful probe for the previous network cannot close or approve the current login form.

**Tests / verification**

- Portal/full/unknown race tests, cancel while polling, network change while typing and no automatic form destruction on success.

<a id="t053"></a>
### T053 — Provision least-privilege NetworkManager authorization

- **Size:** 5
- **Domain:** other
- **Dependencies:** T005, T042, T046
- **Files/outputs:** `config/system/polkit/50-leo-network.rules`, `docs/parent-mode/permissions.md`

**Implementation steps**

1. Compare installed NM policy and measured permission results; add a narrowly scoped polkit rule only for missing scan/network-control/wifi-toggle/modify-own operations.
2. Require leo plus active local session, document upstream default permissions separately, and avoid granting modify.system or wildcard actions.
3. Review restricted-profile ownership alongside action authorization; fail the design review if the required scope cannot be enforced.

**Acceptance criteria**

- Required operations work without a root UI or interactive admin agent.
- The new rule does not newly authorize changing unrelated system profiles or other services.

**Tests / verification**

- Run positive/negative permission tests as leo, inactive/remote session and unrelated user/action; record existing defaults versus grants.

<a id="t054"></a>
### T054 — Provision iwd backend and connectivity checks with rollback

- **Size:** 5
- **Domain:** other
- **Dependencies:** T002, T005, T047
- **Files/outputs:** `config/system/networkmanager/leo-iwd.conf`, `docs/parent-mode/network-provisioning.md`

**Implementation steps**

1. Provide administrator-applied NM/iwd config merging, backups, DHCP/DNS conflict checks and connectivity endpoint/expected-response setup.
2. Validate current saved-network migration, version-supported autoconnect policy and service order in a locally recoverable environment.
3. Document exact rollback of files/services/network profiles and warn against restarting the active remote SSH network.

**Acceptance criteria**

- NetworkManager is the only IP manager and iwd the chosen Wi-Fi backend.
- The configured probe produces meaningful portal/full results or a clearly documented unavailable state.
- Rollback restores the former network configuration without losing prior credentials.

**Tests / verification**

- Rehearse migrate/connect/portal/reboot/rollback on a disposable network with physical access.

<a id="t055"></a>
### T055 — Add network request recovery and sanitized failure taxonomy

- **Size:** 3
- **Domain:** backend
- **Dependencies:** T046, T047, T052
- **Files/outputs:** `app/leo_kiosk/services/wifi.py`

**Implementation steps**

1. Map common NM reasons into stable errors: authentication, authorization, no device, rfkill, DHCP/DNS, scan throttle and unsupported security.
2. Cancel owned requests and reconnect signal subscriptions across backend restart/resume; make Retry bounded and explicit.

**Acceptance criteria**

- Networking failures cannot crash or deadlock the review/home features.
- UI errors never contain secrets or full token-bearing portal URLs.

**Tests / verification**

- Inject each error and late callback into the state machine; verify no pending timer/prompt remains on teardown.

## Phase F: Verification, deployment, and operations

<a id="t056"></a>
### T056 — Complete catalog, review and slot invariant tests

- **Size:** 5
- **Domain:** other
- **Dependencies:** T013, T014, T015, T016, T017, T018
- **Files/outputs:** `app/tests/unit/test_catalog_properties.py`, `app/tests/integration/test_review_transactions.py`

**Implementation steps**

1. Add property/model-based command sequences for import/test/review/select/move/delete/reimport and compare derived state to a small reference model.
2. Exercise migration, backup, read-only and transactional failures with real temporary SQLite files.

**Acceptance criteria**

- All legal sequences preserve nine slots, unique selections and parent decisions.
- Illegal commands fail without partial writes or silent data replacement.

**Tests / verification**

- Run deterministic seeded property tests plus boundary fixtures; preserve minimized regressions.

<a id="t057"></a>
### T057 — Complete gesture noise/timing and input-adapter tests

- **Size:** 3
- **Domain:** other
- **Dependencies:** T019, T020, T021, T026, T027
- **Files/outputs:** `app/tests/unit/test_gesture_properties.py`, `app/tests/integration/test_input_adapter.py`

**Implementation steps**

1. Use Hypothesis/fake clock to generate noisy sequences, releases/repeats, timing boundaries, resets and cooldowns.
2. Exercise fd/hotplug teardown and route changes with a fake input source, without requiring /dev/input access.

**Acceptance criteria**

- No nonmatching event stream emits an action without the exact accepted sequence.
- One physical sequence cannot emit two actions across contexts/devices.

**Tests / verification**

- Run randomized streams plus recorded sanitized Surface volume-event fixtures.

<a id="t058"></a>
### T058 — Complete process isolation and return-path regression tests

- **Size:** 5
- **Domain:** other
- **Dependencies:** T023, T024, T025, T027, T028, T033, T039
- **Files/outputs:** `app/tests/integration/test_sessions.py`

**Implementation steps**

1. Create controlled child/descendant fixtures, including ignored TERM and immediate exit, to verify group cleanup and token ownership.
2. Exercise all return roles, deadlines, stale callback races, profile lifecycle and startup recovery.

**Acceptance criteria**

- No test can kill a process it did not create.
- Every exit mode restores the documented route and preserves correct history/status.

**Tests / verification**

- Run process tests under an isolated user/session and inspect for leftover fixture children/profiles.

<a id="t059"></a>
### T059 — Add NetworkManager D-Bus integration fixtures

- **Size:** 5
- **Domain:** other
- **Dependencies:** T042, T043, T044, T045, T046, T047, T055
- **Files/outputs:** `app/tests/integration/test_networkmanager.py`, `app/tests/fixtures/networkmanager.py`

**Implementation steps**

1. Use python-dbusmock with custom NM AP/secret/connectivity scenarios on an isolated test bus; never target the host system bus.
2. Drive the real GI adapter through scan, activate, cancellation, permission failure, restart and portal transitions.

**Acceptance criteria**

- The adapter is tested beyond mocked Python methods against expected D-Bus method/property shapes.
- Tests cannot reconfigure the developer machine Wi-Fi or use personal credentials.

**Tests / verification**

- Run restart/cancel/secret/SSID-security matrix; assert bus teardown and no pending callbacks.

<a id="t060"></a>
### T060 — Build controlled captive-portal end-to-end fixtures

- **Size:** 5
- **Domain:** other
- **Dependencies:** T050, T051, T052, T059
- **Files/outputs:** `app/tests/fixtures/portal_server.py`, `app/tests/ui/test_portal.py`

**Implementation steps**

1. Serve a local HTTP redirect/login fixture, separate iframe origin, popup case and HTTPS error case; drive online transition through the fake NM backend.
2. Test keyboard input, repeated connection checks, network switch, Cancel/Done and isolation destruction without contacting public portals.

**Acceptance criteria**

- Successful fixture login is touch-capable and no probe reloads a submitted form.
- TLS/security/isolation failure cases stay blocked and return paths work.

**Tests / verification**

- Run under a supported nested Wayland compositor; keep actual Surface touch acceptance separate.

<a id="t061"></a>
### T061 — Add GTK navigation and review workflow smoke tests

- **Size:** 5
- **Domain:** other
- **Dependencies:** T030, T032, T037, T038, T039, T040, T048, T049, T052
- **Files/outputs:** `app/tests/ui/test_parent_workflows.py`

**Implementation steps**

1. Automate widget/controller interactions for parent entry/Exit, row trial, review edits, replacement, deletion, next queue, filters and errors with fake adapters.
2. Capture representative layouts and assert nine tiles/three labels, disabled placeholders and action-bar accessibility when the keyboard is open.

**Acceptance criteria**

- All requested workflows run without internet or physical buttons in UI tests.
- Tests inspect semantic state in addition to screenshots.

**Tests / verification**

- Run marked display tests at target scaling/orientation and verify no blocked main-loop waits.

<a id="t062"></a>
### T062 — Implement structured, privacy-limited diagnostics

- **Size:** 3
- **Domain:** other
- **Dependencies:** T008, T022, T041
- **Files/outputs:** `app/leo_kiosk/diagnostics.py`, `app/run.sh`

**Implementation steps**

1. Use standard logging with component/event/session IDs, sanitized reason codes and no credential/URL-query/general input logging.
2. Replace unbounded ad-hoc logging with documented log destination/rotation behavior and useful startup dependency errors.

**Acceptance criteria**

- Review/network/process problems are diagnosable without passwords, typed text or full portal tokens.
- Log failures do not crash the kiosk and child-facing UI does not show tracebacks.

**Tests / verification**

- Secret-redaction tests for known password/query/token fixtures and log-output size/rotation configuration review.

<a id="t063"></a>
### T063 — Update installation and migrate existing user data safely

- **Size:** 5
- **Domain:** other
- **Dependencies:** T003, T012, T028, T039, T053, T054, T062
- **Files/outputs:** `install-kiosk.sh`, `app/run.sh`

**Implementation steps**

1. Install package directories/assets/catalog and validated runtime packages rather than only the two original Python files.
2. Keep administrator-owned application/config assets separate from leo-owned XDG state/cache/runtime data; seed existing tiles once and back up existing files.
3. Make network migration/privilege changes explicit administrator-approved steps, preserve greetd recovery and do not execute the installer during development.

**Acceptance criteria**

- Repeated installation does not overwrite review data, home layout or remembered settings.
- No unused backwatch process starts, and the app runs as leo without sudo.

**Tests / verification**

- Dry-run/staged installation, upgrade-from-current fixture and failure/rollback rehearsal with file ownership checks.

<a id="t064"></a>
### T064 — Conduct process, browser, input and privilege security review

- **Size:** 5
- **Domain:** other
- **Dependencies:** T023, T028, T050, T051, T053, T054, T062, T063
- **Files/outputs:** `docs/parent-mode/security-review.md`

**Implementation steps**

1. Audit untrusted URL/title/SSID paths, subprocess arguments, filesystem ownership, profile separation, WebKit policy and input-device access.
2. Check least-privilege polkit rules, existing default grants and the limitations of gesture-only parent access/Firefox kiosk mode.
3. Record unresolved risks with an explicit release decision; do not label the setup a complete content-filtering sandbox.

**Acceptance criteria**

- No shell injection path, general root helper, wildcard authorization or disabled browser sandbox/TLS is accepted.
- Risks such as input-group access and arbitrary external web links have documented mitigations/limitations.

**Tests / verification**

- Negative-input/permission tests plus manual browser external-link/download/dialog attempts.

<a id="t065"></a>
### T065 — Execute and record Surface Go hardware acceptance

- **Size:** 8
- **Domain:** other
- **Dependencies:** T004, T005, T056, T057, T058, T059, T060, T061, T063, T064
- **Files/outputs:** `docs/parent-mode/hardware-acceptance.md`

**Implementation steps**

1. Run the complete architecture section 12 matrix on the actual tablet, including gestures while Firefox/portal has focus and touch-only portal forms.
2. Review working/portrait/blocked/broken games, all CTA/slot operations, reboot persistence, timeouts, crash, suspend, Wi-Fi security variants and parent Exit.
3. Record package versions, pass/fail evidence and follow-up defects without saving real credentials/screenshots containing secrets.

**Acceptance criteria**

- Every mandatory matrix row has a measured result; skipped critical rows block release.
- Portal touch keyboard, network rollback and physical gestures pass under the deployed compositor.

**Tests / verification**

- Repeat the critical child/parent/portal flows after a cold boot, not only in the developer session.

<a id="t066"></a>
### T066 — Write parent usage and administrator operations documentation

- **Size:** 3
- **Domain:** other
- **Dependencies:** T037, T052, T054, T063
- **Files/outputs:** `README.md`, `docs/parent-mode/user-guide.md`, `docs/parent-mode/operations.md`

**Implementation steps**

1. Document both exact gestures, three parent tiles, statuses, Keep/Select and CTA behavior, slot replacement, ratings and next queue.
2. Document Wi-Fi/captive login, supported security limits, backups, logs, dependency checks, administrator recovery and what unknown resolution means.
3. Remove obsolete hidden-corner/old gesture/PID-watcher claims from README.

**Acceptance criteria**

- A parent can follow the review/Wi-Fi workflow without knowing Linux commands.
- An administrator can restore data/networking without granting sudo to leo.

**Tests / verification**

- Have a second reader follow a keep/select/delete/login scenario and a documented restore rehearsal.

<a id="t067"></a>
### T067 — Prepare staged rollout, backup and rollback checklist

- **Size:** 3
- **Domain:** other
- **Dependencies:** T018, T063, T065, T066
- **Files/outputs:** `docs/parent-mode/release-checklist.md`

**Implementation steps**

1. Define backup checkpoints for current application, SQLite, home config and network profiles before the approved tablet deployment.
2. Deploy first with a recoverable local session, validate child boot/home then parent/review then Wi-Fi/portal, and name the rollback trigger for each stage.
3. Require explicit administrator approval for privileged changes; preserve the previous version until acceptance.

**Acceptance criteria**

- The release checklist is executable by someone other than the implementer.
- Rollback restores the previous app/network configuration and preserves exportable parent decisions.

**Tests / verification**

- Perform one staged rollback rehearsal and record resulting boot/network/data state.

<a id="t068"></a>
### T068 — Add a read-only support and backup utility

- **Size:** 3
- **Domain:** other
- **Dependencies:** T018, T062, T064
- **Files/outputs:** `tools/leo_diagnostics.py`, `docs/parent-mode/operations.md`

**Implementation steps**

1. Provide nonprivileged checks for schema/version/catalog checksum, nine-slot invariants, active-session summary, imports and network capability state.
2. Offer an explicit safe backup action but omit secrets/browser profiles/full portal URLs from support bundles; default to read-only diagnosis.

**Acceptance criteria**

- A support report can explain catalog/permission/dependency issues without opening the SQLite manually.
- Diagnostics never change Wi-Fi, send process signals or repair/delete data automatically.

**Tests / verification**

- Snapshot sanitized output with secret fixtures and verify read-only mode makes no database/profile changes.
