# Parent-mode implementation status

## Full web UI port (2026-10-25, owner decision; on-device verification pending)

Following the parent-browser PoC below, the owner approved porting **all**
UI to the web stack (architecture.md §12b). Every screen is now an HTML page
on the loopback server (`adapters/ui_server.py`, renamed from
`parent_server.py`) shown in one WebKitGTK view (`ui/window.py`):

- Child home `/`: tiles.json grid, touch-reactive rainbow (JS canvas, same
  parameters as the removed `ui/rainbow.py`), battery gauge (polled via
  `/child-state`, reading moved to `adapters/battery.py`), status line. The
  invisible five-tap exit corner is **not** ported (recorded owner decision:
  removed from the child interface).
- Videos `/videos`: nine random tiles from kiosk_videos.json; a tap POSTs
  `/videos/play`, and the launch engine spawns `videos.py <url>` (thin mpv
  wrapper, ~8 MB, no WebKit) so the `.app-pid`/allowlist contract with
  leopowerd and backwatch is unchanged; when mpv ends the Videos page
  returns. Owner rejected a second WebKit process for the Videos screen.
- **Router**: `ROUTE_FOR_PATH`/`URL_FOR` in `application.py` plus the
  view's `load-changed` → `web_navigated`: route state and gesture pattern
  sets follow the page actually shown. Form POSTs are fetch-based and never
  navigate the view.
- **Gestures** (owner update 2026-10-25): Down/Up returns to child home on
  all launcher-shown parent/video surfaces (`PARENT_SURFACE_PATTERNS`);
  Up/Down/Down enters parent; Down/Down/Up stays default-set (no-op on the
  child home); trial set unchanged; portal gestures close the Firefox
  portal overlay first. Pre-port docs had DDU for these returns — changed
  on owner report that Down/Up was dead there.
- WebKit context menu suppressed; `cursor: none` in child and parent CSS.
- Launch engine extracted headless into `services/tile_launch.py` (voices,
  `alt` fallbacks, deadline TERM→KILL, status messages); assertions ported
  from the removed `tests/ui/test_shell.py`.
- Parent mode `/parent`, `/review`, `/wifi` unchanged, now shown in the same
  view instead of a spawned browser; `parentweb.py` and the GTK parity pages
  (`ui/parent_home.py`, `ui/review_list.py`, `ui/tile_grid.py`) are removed.
- **Firefox removed entirely** (owner decision 2026-10-25): game trials run
  in the launcher's own view (session service keeps tokens/history and adds
  a 30-minute `timed_out` deadline; no browser process, no profiles —
  `adapters/firefox.py` and `adapters/browser_profiles.py` deleted); the
  captive portal is a view navigation with the same gesture exits.
  State-changing server endpoints are route-gated to parent surfaces.
  On-device acceptance: at least one iframe game (e.g. a PBS Springroll
  title) must actually play in WebKitGTK.

Checks: 384 tests, ruff, strict mypy green; the launcher and the pages
verified on the dev machine. **On-device verification of the full port is
pending** — deploy via `install-kiosk.sh` (now also installs
`webkit2gtk-4.1`) and re-run the acceptance checks: touch/scroll/rainbow
feel, tile launches, video playback + Down/Up-hold exit, Down/Up returns
from parent/Wifi/Review/Videos, trial launch/return, memory re-measure.

## WebKitGTK parent browser PoC (2026-10-25, verified on the tablet)

Measured on the Surface Go (PSS via `tools/memprobe.py`, run as root):

| State | Userspace PSS | Parent browser PSS |
|---|---|---|
| Idle, child home | ~340 MB | — |
| Firefox parent browser | 1.22 GiB | ~921 MB across 12 processes |
| WebKitGTK parent browser | ~432 MB | ~225 MB across 3 processes (host 93 + WebProcess 98 + NetworkProcess 34) |

Firefox's 596 MB main process for one server-rendered page also suggests
something inside the Firefox path accumulates; not investigated because the
path was replaced. The Review tile now lists real catalog games (imported at startup from the bootstrap), a row tap launches the actual game in an isolated Firefox kiosk profile, Down/Up returns to an interim editor showing the recorded outcome. Renaming/rating/Keep-Select CTAs are the next UI slice. Parent mode is now reachable in the running launcher: Up/Down/Down opens the grey parent menu, Exit returns to the child home, and Review/Wifi open honest placeholder screens. The old launcher behavior (tiles, fallbacks, voices, time limits) is preserved behind the same window. Not deployed yet — run `leo_deploy` to test on the tablet. The legacy Down/Up watcher still runs alongside until the cutover task.

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

## Catalog trim (2026-10-25, owner instruction)

`web-games.json` was replaced by a trimmed, owner-curated list: 5 providers
(PBS Kids, Starfall, Sesame Street, Nat Geo Kids, Lumni Enfance), 38 games,
each carrying an `iframe_url`. `tools/prepare_catalog.py` now maps
`iframe_url` → `launch_url`, so review trials test the embeddable game
surface (`playable_url = launch_url or source_url`). `catalog/bootstrap.json`
was regenerated (38 games / 5 providers; stale index-based provenance
exclusions deliberately not applied to the new file shape).

Removal semantics: the standing import policy is unchanged (startup import
soft-deletes never-touched games absent from the source and preserves
tested/reviewed/slot-assigned ones). Per the owner's explicit one-time
instruction, `tools/catalog_trim.py` hard-deletes EVERY game absent from the
bootstrap — rows in `home_slots(_v3)`, `launch_sessions(_v3)`,
`review_events` cleared with them; review decisions for surviving games are
untouched. Run it once against the device DB with the kiosk stopped,
as the kiosk user (see the tool docstring). Rehearsed end-to-end on a scratch
database: 97+2 → 38 kept, 61 hard-deleted.

## Review editor with age range + three-dimensional stars (2026-10-26)

The post-trial editor exists: after a trial finishes, the self-refreshing
state page becomes a form — rename (parent_name), **three five-star rows
(fun / educational / production value**, tap stars, per-row clear; all three
required — partial saves re-ask), and a **recommended age range** (two
selects, domain-validated `AgeRange`, both-or-neither, 1–17). CTAs: **Ok**
(save → list), **Ok and see next** (save → next game's editor, wrapping),
**Delete** (parent tombstone; the `{"parent": true}` event marker means
reimports can never resurrect it — refining the auto-tombstone resurrection
rule from 2026-10-25). A trial launch now records `tested_at` on first
trial plus a `tested` event per trial, so the list shows
new/tested/reviewed honestly. Review-list badges show `★fun/edu/prod`.

Schema: v004 adds nullable `games.age_min`/`age_max`; v005 adds nullable
`prod_stars`/`edu_stars`/`fun_stars` (0–5); the legacy 0–100 `rating`
column is no longer written. The migration authorizer gained a read-only
pragma allowlist (`quick_check`/`table_info`/`table_xinfo`) because
`ALTER TABLE ADD COLUMN` consults them internally. Writes run in the server
thread on the thread's own connection (catalog-only state);
session/process state stays marshalled to the main thread. Home-slot
selection (Keep/Select) remains a later slice.

## Home Child picker (2026-10-26, owner request)

New parent-menu tile **Home Child** (`/homechild`, route `HOME_PICKER`): the
review list filtered to reviewed/selected games; a game page with exactly
**Back / Select / Try now**. Select places the game into a chosen slot
(dropdown 1–9, default = the game's slot, else the first empty, else 1)
through `HomeService.place` with the fetched occupant as the explicit
replacement confirmation; the page re-renders with the result or the
validation error. Trials launched here are plain try-outs: Down/Up returns
to the same Home-Child page (`AppController.trial_return`) and Down/Down
performs **no** thumbnail capture. The review editor flow is unchanged.
Not deployed/verified on the tablet yet.

## On-screen keyboard for parent text fields (2026-10-26, owner request)

The kiosk has no OSK daemon (cage + WebKitGTK show nothing on focus), so the
review editor's name field and the Wi-Fi password field were unusable without
the Type Cover. Fix: `adapters/input.has_keyboard()` probes `/dev/input` for
a device with letter keys (read-only capability peek, same boundary as the
volume monitor); `WebUIPages` gets the probe injected and re-checks it at
every editor/Wi-Fi render (Type Cover hotplug picked up on the next page
load). When no keyboard is present, the page embeds an in-page keyboard
(OSK_JS: QWERTY + symbols page, shift, backspace, space, Done) that writes
into the focused input via `setRangeText`; keys use pointerdown so focus
never leaves the field. Detection failure defaults to showing the keyboard.
Not deployed/verified on the tablet yet.

Update (2026-10-26, owner request): the Home Child list now shows **tested**
games too (filter = tested/reviewed/selected), and slot eligibility was
relaxed from reviewed-only to **tested-or-reviewed** (`HomeService._require_placeable`),
so a parent can place a game after trying it without saving stars first. The
empty Home Child list renders a **Back** link to the parent menu (the list
page has one in both states). Architecture §6 invariants and status-derivation
notes updated to match.

Rework (2026-10-26, owner request): Home Child no longer opens the game
list. It now shows the **child home preview** (same labels/colors/thumbs the
child sees; each tile links to its pick list) → tapping a tile opens the
pick list for that tile only → tapping a game places it there (no slot
dropdown anywhere; the tile choice comes first). Replacing an occupied tile
stays explicit-tap-confirmed; placing returns to the preview with a "Tile N:
<name>" note; moves clear the game's previous slot (service invariants).
Per-row **Try** starts a plain try-out whose Down/Up returns to that tile's
pick list, still with no thumbnail capture. Old per-game page and
`/select`/`/launch` routes removed.

Fix (2026-10-26, found on-device): `seed_home` had **no runtime caller** —
home_slots stayed empty, so every Home Child placement failed with "Home
position not found". Startup now seeds the nine slots from the trusted
tiles.json in `_build_catalog_and_sessions` (once, on the empty table;
parent replacements untouched; a broken trusted config is logged and skipped
rather than disabling the kiosk). Also: the Home Child pick list no longer
shows status badges ("tested"/"reviewed") — it is by definition the list of
placeable games; rows show name + stars/ages only.

## My Child: birthday + age filtering (2026-10-26, owner request)

New parent-menu tile **My Child** (`/mychild`, route `MY_CHILD`). The parent
sets the child's birthday with three selects (day/month/year — no keyboard
needed); the page then splits the reviewed/tested catalog by age fit:
"Right for this age" (the child's completed years fall inside the game's
age range; an unset bound is open) and "No age information" (both bounds
unset — an unset range is not a promise, so it gets its own honest group).
Rows are read-only (name + stars/ages); placing games stays in Home Child.
Storage: migration **v007** adds the single-row `child_profile` table;
`ChildRepository`/`ChildService` own persistence and the pure age math
(`parse_birthday` rejects impossible/future/>17-year-old dates). The birthday
is app state in the catalog DB, written on the server thread's own
connection. Deploy note: the device DB gains v007 on next start.

## Per-game playtime ranking (2026-10-27, owner request)

Parent mode gains a **"most played" ranking**: the games the child played,
ranked by total time. Migration **v009** adds `game_playtime`
(`(day, game_id) → seconds`, PRIMARY KEY `(day, game_id)`, FK RESTRICT to
`games`, CHECK `seconds > 0`; indexes on `game_id` and `day, seconds DESC`).
The recording hook already existed for the daily budget: the controller
times each session (`_on_app_exit` for legacy tiles/videos,
`_record_web_usage` for web games) and calls `ScreenTimeService.record` on
exit. `record` now takes an optional `game_id`: when present, the same
whole seconds are also upserted into `game_playtime` **in the same
transaction** (both rows or neither — a bad game id rolls back the budget
row too). Web child games pass `trial_game_id` (captured before
`trial_finished` clears it); legacy tiles and videos have no game identity
and only fill the daily budget, matching `launch_sessions.child_legacy`
(`game_id NULL`). `GamePlaytimeRepository.most_played(limit)` ranks by
all-time `sum(seconds)` per game (ties break by game_id, limit validated
1–100); the day-keyed rows keep per-day splits available for later views.
Not exposed in any page yet — the ranking API exists and is tested
(`tests/unit/test_game_playtime.py`, 10 tests); the parent-mode page is the
next step.

## Daily screen time (2026-10-26, owner request)

My Child gains a **max daily screen time** (minutes: none/0/15/.../240,
domain-validated 0–600; migration **v008** adds
`child_profile.screen_time_minutes` and the per-local-day `screen_time`
usage table). The launch engine records each finished app's elapsed time
(`AppController._on_app_exit` → `ScreenTimeService.record`; review trials
never count; a record failure is logged and never blocks the exit). The
budget resets every local day (usage rows are day-keyed). Child home: a
top-left timer shows the remaining minutes (server-rendered and refreshed
every 2 s via `/child-state`); when the budget is spent (limit 0 or
remaining 0) **every tile renders grey and inert** (`.off` →
`filter: grayscale(1)`, no form/link) and the server refuses
`/launch/*` and `/videos/play` anyway ("No more screen time today!").
Per-tile time limits (tiles.json minutes) are unchanged and still cap each
individual session. Known gap: usage is attributed on app exit, so a
hard power-loss mid-session loses that stretch; videos count when played
through the launcher.

Update (2026-10-26, owner feedback): the Home Child preview now uses the
**child home design exactly** (CHILD_CSS: same grid geometry, ttitle, thumb
tiles with 11px captions, battery, rainbow; the pick message shows as an
`.hcmsg` banner and a fixed `.pback` link returns to the parent menu). The
child home tile label now follows the placed game: `_with_thumbs` replaces
the config label ("TBD") with the slot game's display name (decoding or
lookup failure degrades to "Game", never killing the home).

Update (2026-10-26, owner feedback): My Child's **Save** moved into the
bottom bar (Back left, Save right, `form='mychild-form'` submit attribute).
The review editor's age-range **dropdowns became steppers** (shared
`_stepper`/`STEPPER_JS`; unset bound shows '--', first tap fills the bound,
`✕` clears both bounds — both-empty still means "no age range"). **The OSK
is now unconditional**: the Surface Go exposes an internal "AT Translated
Set 2 keyboard" evdev node with no physical keys, so `has_keyboard()` always
said "present" and hid the keyboard for everyone (found on-device). The
probe is removed; with a Type Cover attached the OSK is redundant but
harmless.

Fix (2026-10-26, found on-device): the review editor's Ok / Ok-and-see-next
buttons sat in a **separate form** from the draft fields, so saving posted
only `action=save` — the typed name (and stars/ages) never reached the
server, and every save failed with "Name must contain 1-80 characters".
The main form is now `id='review-form'` and the save buttons carry
`form='review-form'` (Delete keeps its own form on purpose: it discards the
draft). Regression test pins the wiring.

Update (2026-10-26, owner feedback, four items): (1) the screenshot flash
is now **solid white instantly, held 500 ms, then a 400 ms fade** — the old
fade-in was sometimes imperceptible (`LauncherWindow.flash`). (2) My Child's
Back/Save bar is **fixed to the bottom of the screen** (page class
`mychild`; content gets bottom padding so the lists scroll under it).
(3) **Delete lands on the next game**: the old code looked up the deleted
id after removal, wrapped to -1 and showed the *previous* game; the index
is now captured before deletion. (4) The "Trial returned." outcome banner
is removed from the review editor (`render_editor` lost its `outcome`
parameter; the outcome is still recorded in history and shown nowhere).

## Fixed-size game scaling (2026-10-26, owner request)

Games with **verified design dimensions** (evidence `design`/`iframe`) are
scaled to fill the screen during review trials and Home-Child try-outs: the
controller computes `Dimensions.fit_scale(viewport)` = clamped
`min(view_w/w, view_h/h)` (bounds 0.5–3.0) from the stored design size and
the monitor size, and applies it as a **whole-page WebKit zoom**
(`zoom-text-only=False`, `LauncherWindow.set_page_zoom`); zoom resets to 1
when the trial ends or the view closes. No new catalog attribute — the
existing `dimensions` field is the source of truth. Letterboxing on the
shorter axis is expected. Bootstrap: Dung Beetle Derby got
`1024x768 design` and the asset was re-signed (`source_sha256` covers the
body). Games without verified sizes run at zoom 1. Alternative considered
and rejected for now: injecting `transform: scale(...)` over the game DOM
from the web process — fragile against arbitrary page layouts.

Update (2026-10-26, owner request): all three Nat Geo games whose
`launch_url` starts with `https://images.nationalgeographic.com` — **Crack
The Code 1, Dung Beetle Derby, Letter Predator** — now carry
`dimensions: 1024x768, evidence design` in the bootstrap (re-signed), so
they render scaled to the screen during trials. `tools/prepare_catalog.py`
fixed to prefer per-entry `dimension_evidence` over the provider-level
default, so curated per-game sizes survive regeneration. Recovery note: a
regeneration briefly replaced the curated 38-game bootstrap with a 36-game
one (the curated file was never committed); it was restored from the
deployed checkout on the tablet (`~/leo-kiosk/catalog/bootstrap.json`) —
the curated bootstrap should be committed.

Update (2026-10-26, owner feedback): Delete's confirmation is now an
**in-page modal** styled like the parent UI (dark overlay, rounded panel,
amber text, grey Cancel / red "Yes, delete", big touch targets) instead of
the browser's `window.confirm`. Confirm resubmits the triggering button's
own form; the modal is generic (any `data-confirm` button) and reusable.

Incident (2026-10-26): the whole-page-zoom change called
`view.set_property("zoom-text-only", False)` at startup, and this
WebKitGTK build has no such property — the launcher died on import and the
tablet sat at a dead cage session (black screen). The property is redundant
(WebKit's default zoom already scales the whole page); it is removed and
`set_page_zoom` documents why. Diagnosed via /tmp/leo-launcher.log (the
zombie python3 under cage in `ps` was the tell).

## Child game launches from the home screen (2026-10-26, owner report)

Placed games had **no launch path**: a home tile tap still ran the config
tile's command (`~/kiosk/tbd`), so every placed game said "Ask Papa to fix
this one!". Now `WebUIPages.launch_tile` resolves the tapped position: if
its slot holds a game, the controller starts a **child session**
(`TrialSessionService.start_child_game`, role `child_game` with the slot,
per-tile `minutes` deadline instead of the 30-minute review cap) in the
kiosk view — same machinery as trials: Down/Up returns to the child home,
Down/Down refreshes the game's thumbnail, fixed-size zoom applies, and the
elapsed time is folded into the daily screen-time budget
(`_record_web_usage`; review trials still never count). Legacy tiles keep
the engine path; the screen-time gate covers both. Sessions table rows now
record child launches (role/slot/ended_at), which the schema has supported
since v002.

## Volume buttons control the volume (2026-10-26, owner request)

Until now the volume keys were consumed by the gesture recognizer and
nothing else handled them — taps did nothing. `VolumeInputMonitor` now
treats a **lone press as a volume step**: every press schedules a
`wpctl set-volume -l 1.0 @DEFAULT_AUDIO_SINK@ ±5%` (fire-and-forget; no
pipewire → silent no-op) that fires only if **no further key arrives within
the gesture window (1.1 s, just over max_gap) and no gesture matched** — so
UDD/DU/DD are volume-neutral (each later press cancels the earlier pending
step) and everything else adjusts the default sink. Releases and autorepeats
are ignored (hold-to-repeat is tap-tap-tap). The ~1.1 s delay per step is the
accepted trade for keeping gestures clean. Schedulers/runners are injected;
tests cover lone taps (both directions), gesture neutrality, and
post-gesture taps (cooldown passes → lone again).

Update (2026-10-26, owner feedback): the white screenshot flash is replaced
by a **toast** — "Screenshot captured", themed (dark panel, amber text,
centered top), visible for exactly 500 ms over the game page
(`LauncherWindow.toast`; injected div, no CSS dependency on the foreign
page). The flash method is gone.

## Editor draft survives Try now (2026-10-26, owner report)

Tapping Try now used to throw away the unsaved draft (name, stars, age
range) — the editor re-rendered from the DB after the trial. Worse, a
**partial** star row (one or two dimensions set) could never be saved at
all, because `StarRating` requires all three. Fix: Try now is now a submit
button (`form='review-form'` + `formaction`) that posts the whole draft to
`POST /review/<id>/launch`; the pages provider stores the draft in memory
(`WebUIPages._drafts`, server-thread only, dies with the app on purpose)
and the editor on return renders the stored draft, outranking the DB. The
draft is also kept across validation errors (partial input re-asks with the
input intact) and cleared on a successful save or delete. `render_editor`
gained optional per-dimension star values for partial rows; full
`StarRating`s still come through `stars`. The review list's GET launch is
unchanged (no draft involved).

Update (2026-10-26, owner feedback): **My Child is settings-only** (birthday
steppers + screen-time chips; no game lists — the "Right for this age" /
"No age information" groups are gone). The **age filter moved to Home
Child's pick lists**: when the birthday is known, a pick list shows only
tested/reviewed/selected games whose age range covers the child's age;
games with **no age range are excluded** (an unset range is not a promise
of suitability). Without a birthday the list is unfiltered. The empty pick
list says "Nothing suitable for this age yet." when the age filter removed
everything.

Update (2026-10-26, owner request): in the Review list, tapping a
**reviewed or selected** game opens its editor directly; only **new or
tested** rows launch a trial (the editor is otherwise unreachable). The
draft-survival flow still covers the trial path.
