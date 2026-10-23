# Feature: Parent mode, game review, and iwd-backed Wi-Fi

## Overview

Extend the existing Arch/Surface Go kiosk, not replace its stack: Python/GTK3 under Cage/greetd; Firefox for games; SQLite for local decisions; evdev/pyudev for physical volume input; libnm with NetworkManager's iwd backend for Wi-Fi; isolated ephemeral WebKitGTK 4.1 for captive portals. No HTTP backend, GTK4 migration, direct competing iwd manager or root-running application.

Repository baseline: `leo-kiosk/launcher.py` owns the nine legacy tiles and mutable process state; `backwatch.py` recognizes the old Down/Up shortcut using `.app-pid`; `run.sh` starts both; `install-kiosk.sh` copies individual scripts and installs no new networking/browser GIR dependencies. No test/package harness exists. Preserve existing native/local activities until an explicit home-slot replacement.

Behavior and assumptions:
- **Up, Down, Down** enters a nine-grey-tile parent screen: **Review**, **Wifi**, **Exit** plus six disabled blanks. Exit returns to child home, never a console/logout. Retire the hidden five-tap exit and old Down/Up gesture.
- **Down, Down, Up** stops child playback to home or a review trial to that exact game's editor. Portal return goes to Wifi. Use the full [navigation table](docs/parent-mode/architecture.md#7-navigation-and-volume-gestures), including unsaved-change guards.
- Review status is **new/tested/reviewed/selected**; successful browser spawn means trial attempted, not proven playback. Selected is derived from occupying one of nine stable positions, not a separate flag. Keep existing legacy slots until explicitly replaced.
- Editor: trimmed 1–80-character name, optional integer **0–100%** rating, Keep/Select draft choice and **Delete / Ok / Ok and see next**. Null differs from zero. Save metadata/selection atomically; soft-delete/unselect atomically; require occupant-aware replacement confirmation. Next follows a frozen queue, skips ineligible/deleted IDs and never wraps.
- `web-games.json` is an immutable discovery snapshot: 14 providers, 109 entries (93 labeled games, 16 videos), not verified playback. Preserve originals/provenance, exclude hubs from game trials, retain videos separately, and do not misreport popup/inferred dimensions as measured game resolutions. Normalize to an actual flat catalog file as specified in the architecture.
- Use private per-trial Firefox profiles, a separate persistent child profile, UUID-owned process groups/callbacks and suspend-aware CLOCK_BOOTTIME deadlines. Historical PIDs are never actionable after restart.
- NetworkManager owns DHCP/routes/DNS; iwd handles association. Use async libnm/secret-agent APIs and narrowly scoped active-local-session permissions. Support open/personal networks; enterprise Wi-Fi, cloud sync, video playback, guaranteed web filtering and PIN authentication are out of scope. Hidden-network UI and catalog search are P1 additions.
- Captive login must be **touch-only** with separate portal cookies and intact TLS/sandboxing. Platform keyboard and restricted libnm/iwd spikes are blocking gates. Network/root changes require explicit administrator approval and a physical rollback path; never execute sudo autonomously.

References: [architecture](docs/parent-mode/architecture.md), [original detailed backlog](docs/parent-mode/backlog.md), [original task JSON](docs/parent-mode/tasks.json), [discovery catalog](web-games.json). This execution plan refines the earlier 68-task backlog into **86 atomic tasks**; use the IDs/dependencies/models below for DEEEPR, not the older T001-style graph. Proposed module paths may be split to avoid concurrent edits to a monolithic repository/adapter.

Execution contracts:
- Model assignments come from [`.deeepr/config.json`](.deeepr/config.json): backend **z-ai/glm-5.3-flash**, frontend **deepseek/deepseek-v4-flash**, other **openai/gpt-6.1-sol**. Backend means local services, not a server.
- Target one cohesive change and approximately **≤300 changed implementation/test lines per task**; generated catalog/docs are exempt. If a slice exceeds this, split it before implementation and update dependencies rather than bundling unrelated work. Each task includes focused tests; later verification tasks add cross-component/property/hardware coverage.
- Commands below run from the project root; test paths are outputs to create, not existing files. Use display/Wayland markers only in a configured nested compositor; a headless skip is not hardware acceptance. Pure tests use temporary storage, fake processes and isolated D-Bus, never the host Wi-Fi.
- Domain modules remain GI-free; widgets do not issue SQL, shell commands or process signals. One GLib event loop, cancellable asynchronous networking, caller-owned transaction boundaries and generation/token-checked completions. No secret/general-key logging or disabled TLS/sandboxing.
- Dependencies gate ordering; unrelated slices may run in parallel. P0 includes all release gates; P1/P2 additions do not block P0 delivery. Record failed hardware gates as blocked, not assumed passes. Planning changes no application behavior.

## Tasks

### parent-1 (other)
- **ID:** parent-1
- **Type:** other
- **Precedence:** P0
- **Difficulty:** easy
- **Depends on:** none
- **Model:** openai/gpt-6.1-sol
- **Summary:** Establish isolated test and lint commands
- **Details:** Add leo-kiosk/pyproject.toml and tests/conftest.py for pytest, Ruff and GI-free mypy checks. Provide temporary XDG directories, clock/process fakes and explicit display/hardware markers; configure the leo-kiosk import path. No automated test may access real Wi-Fi credentials or the host system bus. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests; python3 -m ruff check leo-kiosk`.

### parent-2 (other)
- **ID:** parent-2
- **Type:** other
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** none
- **Model:** openai/gpt-6.1-sol
- **Summary:** Record the actual tablet platform and recovery path
- **Details:** Create docs/parent-mode/platform-audit.md with read-only measurements of GTK/GIR/Cage/Firefox/NM/iwd versions, volume-device udev identity, compositor protocols, display scaling, current DHCP/DNS/supplicant ownership and leo permissions. Record physical/SSH recovery before any network migration; do not infer live state from README or run privileged changes. Verify: `python3 --version; cage -v; firefox --version; nmcli general status; systemctl is-active NetworkManager iwd; loginctl session-status; record unavailable commands explicitly`.

### parent-3 (frontend)
- **ID:** parent-3
- **Type:** frontend
- **Precedence:** P0
- **Difficulty:** hard
- **Depends on:** parent-1, parent-2
- **Model:** deepseek/deepseek-v4-flash
- **Summary:** Prove touch-only portal editing under the installed Cage
- **Details:** Add prototypes/portal-keyboard.py and a measured result in docs/parent-mode/portal-keyboard-spike.md. Prototype WebKit2 4.1 ephemeral browsing with non-focus-stealing GTK keys and supported editing commands; test UTF-8, password, delete, submit, HTTPS redirects and cross-origin iframe fields. Failure blocks portal implementation pending an explicit keyboard/compositor decision; never disable sandbox/TLS or substitute a physical keyboard. Verify: `python3 prototypes/portal-keyboard.py; record the touch-only Surface Go pass/fail matrix`.

### parent-4 (backend)
- **ID:** parent-4
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** hard
- **Depends on:** parent-1, parent-2
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Validate libnm/iwd and restricted connection permissions
- **Details:** Add prototypes/nm-smoke.py and docs/parent-mode/network-spike.md. Validate NM 1.0 GIR, async scan/activation, secret-agent callbacks and user-restricted profiles with the installed iwd backend. Administrator-approved migration experiments require a disposable/local recovery setup. Record remember/transient behavior and minimum polkit actions; no root UI or broader permissions as a workaround. Verify: `python3 prototypes/nm-smoke.py --read-only; manually validate a disposable network as leo with administrator approval`.

### parent-5 (backend)
- **ID:** parent-5
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-1
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Define catalog identities and validation primitives
- **Details:** Add domain/catalog.py with MediaType values other=0/video=1/game=2, dimension/orientation evidence, immutable item DTOs and a checked-in UUIDv5 namespace. Conservatively canonicalize HTTP(S) URLs, preserving game-identifying query/fragment data; reject userinfo, control characters and executable schemes. Unknown dimensions/orientation remain distinct from measured portrait data. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/unit/test_catalog_model.py`.

### parent-6 (backend)
- **ID:** parent-6
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-5
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Define review, home and playback contracts
- **Details:** Add domain/reviews.py and domain/sessions.py: review drafts, nullable integer rating 0–100, trimmed 1–80-character names, Keep/Select intent, nine-slot DTOs, launch roles/outcomes and typed validation/conflict/storage errors. Define service Protocols consumed by GTK; no GI/SQL/process imports in domain modules. Reject booleans/fractions as ratings and keep zero distinct from unrated. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/unit/test_review_model.py`.

### parent-7 (frontend)
- **ID:** parent-7
- **Type:** frontend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-1
- **Model:** deepseek/deepseek-v4-flash
- **Summary:** Extract a GTK application shell without changing legacy tiles
- **Details:** Refactor launcher.py into leo_kiosk/application.py and ui/window.py with an injectable Gtk.Stack host; leave a small launcher.py entry point. Preserve tiles.json labels, audio, fallback executables, fullscreen behavior and time limits during extraction. Do not simultaneously change networking or tile data. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/ui/test_shell.py; python3 leo-kiosk/launcher.py in a test display`.

### parent-8 (backend)
- **ID:** parent-8
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-1, parent-6
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Implement safe XDG SQLite bootstrap and migration runner
- **Details:** Add storage/database.py: private XDG data directory, foreign keys, WAL, bounded busy timeout, parameterized transactions and versioned migrations. Back up existing databases using SQLite backup before upgrades. Roll back failed migrations and expose typed errors for corrupt/read-only/full storage; never silently replace data or share a connection across threads. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/integration/test_database.py`.

### parent-9 (backend)
- **ID:** parent-9
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-8
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Create provider, catalog and import-history persistence
- **Details:** Add numbered migrations and storage/catalog.py for providers, games and catalog_imports. Store stable source identity, launch URL, original/parent names, source evidence, tested/reviewed/deleted timestamps, nullable rating and revision. Enforce unique provider/URL identity, integer ratings and foreign keys; repository methods return domain DTOs. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/integration/test_catalog_schema.py`.

### parent-10 (backend)
- **ID:** parent-10
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-9
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Create constrained home slots and launch/review history
- **Details:** Add migration(s), storage/home.py and storage/sessions.py for home_slots, launch_sessions and review_events. Constrain positions to 1–9, unique game assignment and mutually exclusive game/legacy content; prohibit deleting seeded slot rows. Persist role/outcome and UTC history, not actionable historical PIDs or secrets. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/integration/test_state_schema.py`.

### parent-11 (other)
- **ID:** parent-11
- **Type:** other
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-5
- **Model:** openai/gpt-6.1-sol
- **Summary:** Audit the saved discovery catalog without rewriting it
- **Details:** Account for all 109 source records in catalog/provenance.json and docs/parent-mode/catalog-audit.md; preserve web-games.json bytes/checksum. Mark known hub/section URLs ineligible, retain video records separately and label copied/inferred dimensions or Gulli popup sizes as unverified. Do not equate HTTP 200 with playable single-game content or invent a final eligible count. Verify: `python3 -m json.tool web-games.json; python3 -m json.tool catalog/provenance.json; reconcile every source index with its checksum`.

### parent-12 (backend)
- **ID:** parent-12
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-5, parent-11
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Generate the flat catalog and JSON schema deterministically
- **Details:** Add tools/normalize_catalog.py, catalog/games.schema.json and generated catalog/games.json. Emit exactly name/url/is_landscape/width/height/type; use 0/0 for unknown size, 0/1/2 type mapping and an orientation_known sidecar flag for unknown boolean placeholders. Preserve provenance/exclusions and queries/fragments; validate using jsonschema Draft 2020-12. Verify: `python3 tools/normalize_catalog.py --check; PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/unit/test_normalize_catalog.py`.

### parent-13 (backend)
- **ID:** parent-13
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-12, parent-9
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Import catalog snapshots atomically and idempotently
- **Details:** Add services/catalog_import.py. Validate full catalog/provenance before one transaction; upsert only source metadata by stable identity and record checksums/counts. Never reset parent names, ratings, history, slots or tombstones, and retain locally reviewed records removed from later source snapshots. No network fetches during import; invalid input leaves the previous catalog intact. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/integration/test_catalog_import.py`.

### parent-14 (backend)
- **ID:** parent-14
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-13, parent-10
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Expose catalog queries and derived review statuses
- **Details:** Add services/catalog.py queries with deterministic provider/source-name/ID ordering, game eligibility, plain-text display fields and last-trial evidence. Derive selected > reviewed > tested > new; deleted is hidden/archive metadata, not a fifth primary badge. Videos/hubs are excluded from the default playable queue; repeated trials never downgrade reviewed/selected status. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/unit/test_catalog_queries.py`.

### parent-15 (backend)
- **ID:** parent-15
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-10
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Seed the existing nine home activities exactly once
- **Details:** Add services/home_seed.py to validate trusted tiles.json and insert nine stable positions preserving argv, fallback, label, color, audio ID and limits. Subsequent startup must not overwrite parent replacements. Catalog entries can never supply executable commands; reject malformed seed config without partially filling home. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/integration/test_home_seed.py`.

### parent-16 (backend)
- **ID:** parent-16
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-14, parent-15
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Implement transactional slot assignment primitives
- **Details:** Add services/home.py operations for explicit placement/replacement/move/unselection. Only reviewed nondeleted games are eligible; enforce unique occupancy and nine positions. Require explicit occupant-aware replacement authorization, leave moved-from positions empty, and retain displaced games as reviewed. Support caller-owned transactions for atomic review saves; never auto-evict or silently swap. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/unit/test_home_slots.py`.

### parent-17 (backend)
- **ID:** parent-17
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** hard
- **Depends on:** parent-16, parent-6
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Save review metadata and selection as one transaction
- **Details:** Add services/reviews.py save_review(game_id, expected_revision, draft, target_slot, replacement_confirmation). Validate name/rating/eligibility, update reviewed timestamp/revision, apply Keep/Select and append history atomically. Keep unselects an existing assignment; Select preserves the current slot unless a move is requested. Rollback/conflict errors retain the UI draft and cannot advance the queue. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/integration/test_review_save.py`.

### parent-18 (backend)
- **ID:** parent-18
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-17
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Soft-delete games and remove selection atomically
- **Details:** Add delete_game to the review service with revision checking, tombstone, audit event and slot clearing in one transaction. Do not persist unsaved name/rating edits during deletion. Reimport must not resurrect deleted records; all other slot positions and displaced legacy definitions remain untouched. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/integration/test_review_delete.py`.

### parent-19 (backend)
- **ID:** parent-19
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-14
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Implement immutable review-next queue behavior
- **Details:** Add domain/review_queue.py to snapshot displayed eligible IDs at row activation and advance from the current position. Skip deleted/ineligible IDs, never wrap, and do not reorder after rename/rating/filter/import changes. Represent queue end and next-launch failure explicitly; widgets must not infer next from live row indices. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/unit/test_review_queue.py`.

### parent-20 (backend)
- **ID:** parent-20
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-10, parent-17
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Recover abandoned trials and expose safe data backups
- **Details:** Add services/recovery.py to mark unfinished historical sessions abandoned and offer the latest trial for review without automatically relaunching or signaling stored PIDs. Provide SQLite backup/export with schema/checksum metadata; restore only while stopped. Preserve committed decisions on restart and report corruption/read-only failures without destructive repair. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/integration/test_recovery.py`.

### parent-21 (backend)
- **ID:** parent-21
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-1
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Implement the pure three-tap gesture recognizer
- **Details:** Add domain/gestures.py accepting volume key-downs only: UDD enters parent, DDU returns. Use injected monotonic time, maximum 1-second gaps/2-second sequence, consumed matches and 500-ms cooldown. Ignore repeats/releases/unrelated keys, keep valid wrong-prefix suffixes and expose reset(reason). Old DU must not match; one event cannot belong to two emitted actions. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/unit/test_gestures.py`.

### parent-22 (backend)
- **ID:** parent-22
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-21, parent-2
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Read only configured volume devices through evdev/GLib
- **Details:** Add adapters/input.py with nonblocking evdev fds and GLib watches. Filter capabilities and measured stable device identity, avoiding duplicate physical sources; forward only volume presses without grabbing/replaying normal volume events. No all-key logging or PID killing. Permission/device failures become diagnostics while the launcher remains usable. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/unit/test_input_monitor.py`.

### parent-23 (backend)
- **ID:** parent-23
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-22
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Rescan volume input devices on hotplug
- **Details:** Add a pyudev monitor adapter integrated through GLib; reuse input filtering for add/remove events and close watches/fds exactly once. Reset partial gestures after removal and expose rescan for wake. Duplicate notifications, inaccessible devices and reconnects must neither leak fds nor duplicate gestures. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/unit/test_input_hotplug.py`.

### parent-24 (backend)
- **ID:** parent-24
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-6
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Manage separate private Firefox profiles
- **Details:** Add adapters/browser_profiles.py for per-trial temporary profiles and a persistent child-only profile under private XDG paths. Apply version-compatible policies/preferences for downloads, external handlers and prompts without disabling sandbox/TLS. Clean temporary data only after owned browser shutdown; reject profile locks safely and never use the administrator/default profile. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/unit/test_browser_profiles.py`.

### parent-25 (backend)
- **ID:** parent-25
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-24, parent-5
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Launch game URLs in an isolated Firefox process group
- **Details:** Add adapters/firefox.py building argv for --no-remote/--new-instance/--profile/--kiosk with validated HTTP(S) URLs and native Wayland environment. Use Popen(start_new_session=True), never a shell. Return a captured process/group handle, not a PID file; spawn failures leave GTK visible. Route trusted legacy Firefox content through an owned isolated instance without accepting file URLs from catalog data. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/unit/test_firefox_adapter.py`.

### parent-26 (backend)
- **ID:** parent-26
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-25, parent-10
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Own launch sessions and record trial attempts
- **Details:** Add services/sessions.py with UUID token, role, game/slot ID, return context, captured process and starting/running/stopping/finished phases. Permit one external activity; preserve trusted legacy fallback/audio behavior through adapters/legacy_apps.py. Record successful spawn as tested/trial attempted, not proven playback; failed spawn remains new. Poll asynchronously and inject process/clock interfaces. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/unit/test_sessions.py`.

### parent-27 (backend)
- **ID:** parent-27
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** hard
- **Depends on:** parent-26
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Make process termination and exit callbacks token-safe
- **Details:** Implement idempotent stop/exit cleanup: TERM the captured owned group, escalate after three seconds, account for descendants and emit one final outcome. Every callback checks its captured token and cancels timer sources; never act on whichever process is now current. Natural exit, repeated gestures and timeout races must restore a route without killing a newer launch. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/unit/test_session_termination.py`.

### parent-28 (backend)
- **ID:** parent-28
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-27, parent-23
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Use suspend-aware deadlines and wake cleanup
- **Details:** Add adapters/power.py for Gio/logind sleep signals and CLOCK_BOOTTIME-based session deadlines. Child per-slot limits and default 30-minute review trials include sleep, unaffected by wall-clock corrections. On wake reset gestures, rescan input, refresh network through an injected hook and expire overdue sessions; UTC history cannot resume deadlines after reboot. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/unit/test_session_deadlines.py`.

### parent-29 (backend)
- **ID:** parent-29
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-6, parent-19
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Define typed routes and parent-session navigation
- **Details:** Add services/navigation.py implementing architecture section 7 for CHILD_HOME/PARENT_HOME/REVIEW_LIST/TRIAL/EDITOR/WIFI/PORTAL/CHILD_ACTIVITY. Store return game, queue and list position outside widgets; model dirty-editor navigation confirmation and pending stop transitions. Exit means child home, never Gtk.main_quit/Cage logout; child close and review close have distinct destinations. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/unit/test_navigation.py`.

### parent-30 (frontend)
- **ID:** parent-30
- **Type:** frontend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-7, parent-22, parent-29, parent-27
- **Model:** deepseek/deepseek-v4-flash
- **Summary:** Dispatch gestures while GTK or Firefox is foregrounded
- **Details:** Add application-level input/navigation binding. UDD stops owned playback before parent home; DDU stops review trial before its editor or child activity before child home. Reset recognizer on route changes and restore the existing window after failures/exits; do not depend on GTK key focus or open duplicate windows. Test portal/dirty-editor cases using fake views. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/ui/test_gesture_routes.py`.

### parent-31 (other)
- **ID:** parent-31
- **Type:** other
- **Precedence:** P0
- **Difficulty:** easy
- **Depends on:** parent-30, parent-28
- **Model:** openai/gpt-6.1-sol
- **Summary:** Retire the old watcher and hidden kiosk-exit corner
- **Details:** Update run.sh to run the launcher alone; retire backwatch.py/.app-pid signaling and remove the five-tap overlay from the child interface. Clean up input/browser resources on normal exit, ignore historical PID files and retain administrator recovery via documented SSH/console rather than a child-accessible secret exit. Keep logind power-button behavior unchanged. Verify: `sh -n leo-kiosk/run.sh; PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/ui/test_session_cutover.py`.

### parent-32 (frontend)
- **ID:** parent-32
- **Type:** frontend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-7
- **Model:** deepseek/deepseek-v4-flash
- **Summary:** Extract shared nine-position tile geometry
- **Details:** Add ui/tile_grid.py/styles.css with homogeneous three-by-three expansion, existing margins/spacing and large touch targets. Accept immutable tile models and separate child/parent styles; blank tiles have no handler or focus stop. Preserve nine positions when empty, support tablet scaling/orientation and wrap/ellipsize names rather than shrinking hit areas. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/ui/test_tile_grid.py`.

### parent-33 (frontend)
- **ID:** parent-33
- **Type:** frontend
- **Precedence:** P0
- **Difficulty:** easy
- **Depends on:** parent-32, parent-29
- **Model:** deepseek/deepseek-v4-flash
- **Summary:** Add the grey parent menu and safe Exit
- **Details:** Add ui/parent_home.py: Parent title, nine grey tiles, exact Review/Wifi/Exit labels on the first three and six disabled blank tiles. Route through the controller and clear parent mode on Exit; never quit the GTK main loop. Expose accessibility names without adding visible placeholder labels. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/ui/test_parent_home.py`.

### parent-34 (frontend)
- **ID:** parent-34
- **Type:** frontend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-33, parent-14, parent-19
- **Model:** deepseek/deepseek-v4-flash
- **Summary:** Render playable catalog rows and capture stable review queues
- **Details:** Add ui/review_list.py with touch scrolling, plain-text name/status/provider/rating/evidence and selected-game versus occupied-slot counts. Row activation emits game ID plus a frozen displayed queue; secondary Edit review reopens metadata without playback. Preserve scroll anchor on return, show offline/empty/error states and never label a trial attempt as successful playback. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/ui/test_review_list.py`.

### parent-35 (frontend)
- **ID:** parent-35
- **Type:** frontend
- **Precedence:** P1
- **Difficulty:** medium
- **Depends on:** parent-34
- **Model:** deepseek/deepseek-v4-flash
- **Summary:** Add optional provider, status and text filters
- **Details:** Extend the review list with persistent filter/search state and deterministic ordering. Keep videos in a separately labeled discovery-only view, not trial/selection actions. Capture next queues from eligible displayed IDs; filtering/renaming/deleting the anchor restores the nearest valid row without changing an active queue. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/ui/test_review_filters.py`.

### parent-36 (frontend)
- **ID:** parent-36
- **Type:** frontend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-34, parent-26, parent-27, parent-29
- **Model:** deepseek/deepseek-v4-flash
- **Summary:** Connect row trials to the correct review editor context
- **Details:** Add review trial orchestration with immediate loading feedback and DDU instructions; block repeat taps while starting. Open the actual item URL and on gesture/natural exit/crash/timeout return the captured game/queue/outcome to the editor. Failed spawn leaves the list/retry state intact and does not mark tested. No automatic approval on return. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/ui/test_review_trial.py`.

### parent-37 (frontend)
- **ID:** parent-37
- **Type:** frontend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-32
- **Model:** deepseek/deepseek-v4-flash
- **Summary:** Build a reusable non-focus-stealing touch keyboard
- **Details:** Add ui/keyboard.py key layouts, show/hide, letters/numbers/symbols, shift, delete and submit callbacks against a typed input-target interface. Use touch-sized controls and resize/pan forms so fields and bottom CTAs remain reachable. Keep key presses out of logs/history; verify non-focus-stealing behavior without relying on compositor-global keyboards. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/ui/test_keyboard.py`.

### parent-38 (frontend)
- **ID:** parent-38
- **Type:** frontend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-37
- **Model:** deepseek/deepseek-v4-flash
- **Summary:** Implement GTK editable input targets
- **Details:** Add Gtk.Editable/numeric target adapters for keyboard insertion, selection replacement, Unicode deletion, cursor movement and submit. Preserve active-field focus and masked password behavior when tapping keyboard controls; clear transient references on hide/destroy. Do not retain password copies or overwrite another field after focus changes. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/ui/test_editable_keyboard.py`.

### parent-39 (frontend)
- **ID:** parent-39
- **Type:** frontend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-6, parent-38, parent-36
- **Model:** deepseek/deepseek-v4-flash
- **Summary:** Build review fields and Keep/Select draft state
- **Details:** Add ui/review_editor.py with original/display name, nullable integer 0–100 rating slider/numeric controls, Keep/Select choice and read-only source/status/outcome/evidence. Validate locally without writing SQL; initialize selected games with their slot and preserve null versus zero. Keep editor drafts separate from committed history and expose service callbacks for actions implemented separately. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/ui/test_review_editor.py`.

### parent-40 (frontend)
- **ID:** parent-40
- **Type:** frontend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-39, parent-16, parent-32
- **Model:** deepseek/deepseek-v4-flash
- **Summary:** Add explicit home-slot selection and replacement confirmation
- **Details:** Add ui/slot_picker.py showing nine numbered positions and current legacy/game occupant names. New selections require a position; occupied targets require confirmation naming the displaced entry, and moves clear the old slot. Keep the choice as draft intent until save; Cancel must not alter the actual home layout. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/ui/test_slot_picker.py`.

### parent-41 (frontend)
- **ID:** parent-41
- **Type:** frontend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-40, parent-17
- **Model:** deepseek/deepseek-v4-flash
- **Summary:** Implement Ok with atomic review/selection save feedback
- **Details:** Connect editor Ok to save_review and return to the preserved list only after commit. Disable repeat submission, show field/conflict/storage errors and retain all draft values on failure; refresh home/list from committed state. Keep the bottom action bar reachable with the keyboard open. No partial metadata/selection success or implicit selection of an arbitrary slot. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/ui/test_review_ok.py`.

### parent-42 (frontend)
- **ID:** parent-42
- **Type:** frontend
- **Precedence:** P0
- **Difficulty:** easy
- **Depends on:** parent-41, parent-18
- **Model:** deepseek/deepseek-v4-flash
- **Summary:** Implement Delete confirmation and list return
- **Details:** Connect Delete with a confirmation naming the game and affected home position; commit tombstone/unselection through the service and return to the nearest remaining row. Cancel retains the draft; failure retains editor and selection. Do not save draft name/rating through the destructive action. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/ui/test_review_delete.py`.

### parent-43 (frontend)
- **ID:** parent-43
- **Type:** frontend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-41, parent-19, parent-36
- **Model:** deepseek/deepseek-v4-flash
- **Summary:** Implement Ok and see next without queue reordering
- **Details:** Reuse the successful Ok transaction, then launch the next eligible frozen ID. Skip deleted/excluded entries, stop with a completion state rather than wrap, and never advance after failed save. If next spawn fails, show the next item/retry context, not the previous editor; disable duplicate requests. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/ui/test_review_next.py`.

### parent-44 (frontend)
- **ID:** parent-44
- **Type:** frontend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-41, parent-29
- **Model:** deepseek/deepseek-v4-flash
- **Summary:** Guard navigation away from unsaved reviews
- **Details:** Bind editor dirty state to navigation and provide Save/Discard/Cancel on return/parent gestures and page changes. Save uses the same transaction, Discard loses only draft edits, Cancel preserves route/keyboard/focus. Clean editors leave without prompting; failed Save must not navigate or downgrade recorded trial evidence. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/ui/test_review_dirty.py`.

### parent-45 (frontend)
- **ID:** parent-45
- **Type:** frontend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-32, parent-15, parent-16, parent-26, parent-41, parent-42
- **Model:** deepseek/deepseek-v4-flash
- **Summary:** Render committed mixed home slots and launch child games
- **Details:** Add ui/child_home.py binding the nine persisted positions to native/game/empty tiles. Preserve un-replaced legacy commands/audio/colors/limits, use parent names and deterministic game colors, disable empties and default new-game limits to 20 minutes. Game launches use the child profile and child return route; exiting parent refreshes only committed assignments. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/ui/test_child_home.py`.

### parent-46 (frontend)
- **ID:** parent-46
- **Type:** frontend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-20, parent-44, parent-45
- **Model:** deepseek/deepseek-v4-flash
- **Summary:** Show safe recovery and actionable local errors
- **Details:** Add ui/diagnostics.py views for missing browser/input, profile lock, catalog validation, database migration/read-only/corruption and recovered abandoned trials. Offer Retry/Back/recovered editor without resetting committed data; sanitize text and preserve draft/filter context after transient errors. A failed database must not appear as a successful empty catalog. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/ui/test_recovery_views.py`.

### parent-47 (backend)
- **ID:** parent-47
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-1
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Define GI-free Wi-Fi DTOs and request ownership
- **Details:** Add domain/network.py and services/wifi.py contracts for SSID bytes/security families/devices/profiles/connectivity, cancellable requests and generation IDs. Define unavailable/off/blocked/scanning/connecting/checking/portal/limited/online/error states. Ignore stale completion after network changes; distinguish association from internet access and unknown from offline. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/unit/test_wifi_model.py`.

### parent-48 (backend)
- **ID:** parent-48
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-47, parent-4
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Implement libnm availability, device and permission lifecycle
- **Details:** Add adapters/nm_client.py pinned to NM 1.0, with asynchronous construction where supported, subscriptions and DTO snapshots. Handle daemon absence/restart, device removal, radio/rfkill and permission changes; unsubscribe safely and reconnect without duplicate signals. Do not assume a polkit authentication agent exists or synchronously block GTK. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/unit/test_nm_client.py`.

### parent-49 (backend)
- **ID:** parent-49
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-48
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Implement rate-limited asynchronous Wi-Fi scans
- **Details:** Add adapters/nm_scan.py with per-device request_scan, AP-change subscription and one outstanding cancellable request. Expose scanning/throttle/errors through the service; old scans cannot publish after device removal or generation changes. No nmcli/iwctl shell output parsing and no direct competing iwd client. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/unit/test_nm_scan.py`.

### parent-50 (backend)
- **ID:** parent-50
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-49
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Normalize access points without unsafe SSID merging
- **Details:** Add domain/access_points.py grouping APs by SSID bytes and compatible security family; compute strongest/current/saved indicators and safe display names. Preserve hidden/undecodable SSIDs and never combine an open AP with a protected saved connection of the same text name. Render raw values as plain text only. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/unit/test_access_points.py`.

### parent-51 (backend)
- **ID:** parent-51
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** hard
- **Depends on:** parent-48
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Register a request-scoped NetworkManager secret agent
- **Details:** Add adapters/secret_agent.py implementing NM.SecretAgentOld callbacks and matching credential prompts/cancellations. Answer only a current parent-owned activation, reject unrelated/background/stale requests, unregister on teardown and handle daemon restart. Keep secrets out of argv/logs/SQLite and clear pending buffers; use the measured remember/transient contract, not assumptions about memory erasure. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/unit/test_secret_agent.py`.

### parent-52 (backend)
- **ID:** parent-52
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-48, parent-50, parent-51
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Activate compatible saved Wi-Fi profiles asynchronously
- **Details:** Add adapters/nm_connections.py saved activation with device/AP compatibility checks and generation ownership. Wait for device/active-connection state rather than treating method success as Online. Surface unsupported enterprise/security, authentication, permission and DHCP failures without changing profile restrictions or downgrading security. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/unit/test_saved_activation.py`.

### parent-53 (backend)
- **ID:** parent-53
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** hard
- **Depends on:** parent-52
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Create validated open and personal network profiles
- **Details:** Add adapters/nm_profile.py creating user-restricted open/WPA2/supported WPA3 profiles, including hidden-network backend parameters. Validate security/credentials, require explicit open-network consent and use measured transient versus Remember behavior. Never put secrets on a command line, grant system-wide profile modification, or silently enable an unsupported enterprise configuration. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/unit/test_nm_profiles.py`.

### parent-54 (backend)
- **ID:** parent-54
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-53
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Cancel owned connection attempts and offer safe fallback
- **Details:** Extend the Wi-Fi service to cancel requests and deactivate only the still-owned pending activation. A late cancel for A must not disconnect current B. Retain the previous compatible saved profile and offer bounded explicit reconnect after a failed switch; avoid automatic retry loops and cancel stale credential prompts on navigation. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/unit/test_wifi_cancel.py`.

### parent-55 (backend)
- **ID:** parent-55
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-54
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Implement explicit disconnect and authorized profile forgetting
- **Details:** Add Wi-Fi service disconnect/forget methods checking current permissions and user-profile ownership. Confirm forgetting, prevent deletion/modification of administrator/system profiles and retain current state on denial. Do not implement a root helper or shell fallback when authorization fails. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/unit/test_wifi_forget.py`.

### parent-56 (backend)
- **ID:** parent-56
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-48, parent-52
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Expose connectivity states and bounded rechecks
- **Details:** Add adapters/nm_connectivity.py handling NM check availability/configured URI and unknown/none/limited/portal/full. Use async cancellable single-flight checks with request generations; stop timers when leaving or changing connection. Disabled/blocked probes mean unverified connectivity, not definitive offline; provide manual login intent without hard-coded third-party probes. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/unit/test_connectivity.py`.

### parent-57 (frontend)
- **ID:** parent-57
- **Type:** frontend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-33, parent-50, parent-55, parent-56
- **Model:** deepseek/deepseek-v4-flash
- **Summary:** Render the Wi-Fi list and operation/status controls
- **Details:** Add ui/wifi.py for radio/Scan/AP rows, signal/security/saved/current text, connect/disconnect/forget and Sign in/Open login. Bind immutable service snapshots and loading/disabled/error states; expose permission/rfkill/service failures without blocking GTK. A connected AP is not labeled Online before connectivity confirms it, and unknown check state remains visible. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/ui/test_wifi_screen.py`.

### parent-58 (frontend)
- **ID:** parent-58
- **Type:** frontend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-57, parent-38, parent-51, parent-53
- **Model:** deepseek/deepseek-v4-flash
- **Summary:** Add touch credentials, Remember and open-network consent
- **Details:** Add ui/wifi_credentials.py with masked password/show toggle, Remember, validation/retry and explicit open-network warning. Bind secret prompts to the matching current activation; cancel/finish clears transient values and stale prompts cannot reuse old input. Keep forms and actions reachable using touch without password logging or catalog persistence. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/ui/test_wifi_credentials.py`.

### parent-59 (frontend)
- **ID:** parent-59
- **Type:** frontend
- **Precedence:** P1
- **Difficulty:** medium
- **Depends on:** parent-58
- **Model:** deepseek/deepseek-v4-flash
- **Summary:** Add an explicit hidden personal-network form
- **Details:** Extend the credentials UI with SSID/security fields for supported hidden personal networks, using the existing profile builder and touch keyboard. Validate SSID byte limits and supported security, show unsupported enterprise guidance, and keep discovered AP grouping unchanged. Cancel must not create a persistent profile or disturb another active connection. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/ui/test_hidden_wifi.py`.

### parent-60 (frontend)
- **ID:** parent-60
- **Type:** frontend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-3, parent-7, parent-47
- **Model:** deepseek/deepseek-v4-flash
- **Summary:** Create connection-scoped ephemeral portal browser contexts
- **Details:** Add ui/portal_context.py pinned to WebKit2 4.1. Create sandboxed ephemeral context/view per portal workflow, with no privileged launcher JS bridge or shared Firefox cookies. Destroy context on connection change/exit and contain permitted child views in the same isolation boundary. Handle missing GIR/load failures without disabling the sandbox or TLS. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/ui/test_portal_context.py`.

### parent-61 (frontend)
- **ID:** parent-61
- **Type:** frontend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-60
- **Model:** deepseek/deepseek-v4-flash
- **Summary:** Implement safe portal navigation and visible controls
- **Details:** Add ui/portal.py host warning, Back/Reload/keyboard/Check/Done/Cancel controls. Start only from explicit parent intent at the administrator-configured HTTP entrypoint; allow HTTP/HTTPS redirects and controlled popups but reject downloads/custom/file schemes/external applications/privileged permission prompts. Keep certificate failures blocked and never log full token-bearing URLs. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/ui/test_portal_navigation.py`.

### parent-62 (frontend)
- **ID:** parent-62
- **Type:** frontend
- **Precedence:** P0
- **Difficulty:** hard
- **Depends on:** parent-3, parent-38, parent-60
- **Model:** deepseek/deepseek-v4-flash
- **Summary:** Productionize focused-frame WebKit touch editing
- **Details:** Add a WebKit input-target adapter using the proven supported editing/capability APIs and non-focus-stealing keyboard. Cover UTF-8, password fields, delete, cursor/submit, redirect and iframe focus recovery. Reproduce the prototype under Cage; failure remains release-blocking rather than introducing insecure injected bridges or requiring an external keyboard. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/ui/test_portal_keyboard.py; repeat the measured Surface Go touch matrix`.

### parent-63 (backend)
- **ID:** parent-63
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-56, parent-54
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Implement connection-owned portal state and polling
- **Details:** Add services/portal.py with one bounded connectivity check about every five seconds, tied to current connection/generation. Never reload or POST login forms to probe access. Full connectivity offers success/Done without destroying an in-progress form; unknown/limited/disabled checks retain manual retry. Cancel/network change stops pending probes and invalidates old results. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/unit/test_portal_state.py`.

### parent-64 (frontend)
- **ID:** parent-64
- **Type:** frontend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-61, parent-62, parent-63, parent-58, parent-30
- **Model:** deepseek/deepseek-v4-flash
- **Summary:** Connect portal login, rechecks and return navigation
- **Details:** Wire Sign in/Open login to the isolated view, state controller and keyboard. DDU closes to Wifi; UDD closes to parent home; Done/Cancel release context/timers and do not invent Online status. Network change destroys old context, and a stale successful check cannot approve a different connection. Keep Back/Cancel usable while loading. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/ui/test_portal_routes.py`.

### parent-65 (backend)
- **ID:** parent-65
- **Type:** backend
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-55, parent-56, parent-63
- **Model:** z-ai/glm-5.3-flash
- **Summary:** Map networking failures and recover subscriptions after resume
- **Details:** Add stable sanitized error mapping for auth/permissions/rfkill/no-device/throttle/DHCP/DNS/service loss. Reconcile pending requests on daemon restart/resume, release secret prompts and resubscribe exactly once. Provide explicit bounded Retry without impairing catalog/home operation or leaking credentials/token URLs in messages. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/unit/test_wifi_recovery.py`.

### parent-66 (other)
- **ID:** parent-66
- **Type:** other
- **Precedence:** P0
- **Difficulty:** hard
- **Depends on:** parent-4, parent-55
- **Model:** openai/gpt-6.1-sol
- **Summary:** Prepare and test narrow NetworkManager authorization
- **Details:** Add system/polkit/50-leo-network.rules and docs/parent-mode/permissions.md only for measured missing wifi.scan/network-control/enable-disable-wifi/settings.modify.own actions, scoped to leo plus active local session. Review installed defaults and profile restrictions; no wildcard/modify.system grants. Administrator approval is required to install, and inability to enforce scope blocks release. Verify: `Review rule syntax; record positive/negative action/profile tests as leo, an inactive session and another user on the target`.

### parent-67 (other)
- **ID:** parent-67
- **Type:** other
- **Precedence:** P0
- **Difficulty:** hard
- **Depends on:** parent-2, parent-4, parent-56
- **Model:** openai/gpt-6.1-sol
- **Summary:** Prepare iwd backend and connectivity-probe migration with rollback
- **Details:** Add system/networkmanager/leo-iwd.conf and a merge/rollback runbook. Configure NM wifi.backend=iwd, measured NM-owned autoconnect, iwd EnableNetworkConfiguration=false and an administrator-selected valid HTTP connectivity probe. Audit conflicting DHCP/DNS managers and saved-profile migration first. Back up existing configuration; never restart a live remote network without physical recovery/approval. Verify: `Validate candidate files against installed versions; rehearse association/probe/reboot/rollback on a disposable locally recoverable network`.

### parent-68 (other)
- **ID:** parent-68
- **Type:** other
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-2, parent-23
- **Model:** openai/gpt-6.1-sol
- **Summary:** Document and provision the minimum input-device access
- **Details:** Add a targeted udev permission candidate for the measured volume device and docs/parent-mode/input-permissions.md. Verify add/remove/resume access as leo without evdev grabs or general keyboard logging. Avoid wildcard input access; if existing input-group membership is temporarily necessary, record the explicit security exception and do not claim keyboard isolation. Verify: `udevadm info --query=property --name=/dev/input/<audited-device>; verify selected-device readability as leo with administrator-approved rule installation`.

### parent-69 (other)
- **ID:** parent-69
- **Type:** other
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-1
- **Model:** openai/gpt-6.1-sol
- **Summary:** Add structured sanitized application logging
- **Details:** Add diagnostics.py using standard logging, event/session IDs and stable reason codes. Strip secrets, typed input, full portal URL queries and raw all-key events; define bounded log destination/rotation behavior and safe logging failure fallback. Do not turn diagnostic output into GTK markup or expose tracebacks to child screens. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/unit/test_diagnostics.py`.

### parent-70 (other)
- **ID:** parent-70
- **Type:** other
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-2, parent-3, parent-4
- **Model:** openai/gpt-6.1-sol
- **Summary:** Add validated runtime dependencies to installation
- **Details:** Update only the package/dependency section of install-kiosk.sh for python-evdev/python-pyudev/python-jsonschema/libnm/networkmanager/iwd/polkit/WebKitGTK 4.1 and existing GTK/Firefox packages after repository validation. Keep developer dependencies separate and document GIR smoke checks. No pip system-Python mutation or automated networking restart; this task prepares changes, not executes sudo. Verify: `bash -n leo-kiosk/install-kiosk.sh; review Arch package mappings and run nonprivileged import/GIR version smoke checks`.

### parent-71 (other)
- **ID:** parent-71
- **Type:** other
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-70, parent-12, parent-31, parent-66, parent-67, parent-68
- **Model:** openai/gpt-6.1-sol
- **Summary:** Install modules/catalog and preserve mutable state on upgrades
- **Details:** Update installer asset copying to include the Python package, CSS, migrations and generated catalog/provenance from project-root paths. Separate administrator-owned code/trusted config from leo-owned XDG data/cache/runtime, preserve existing reviews/slots and back up replaced files. Make privileged network/policy application explicit opt-in administrator steps; retain greetd/logind recovery configuration. Verify: `bash -n leo-kiosk/install-kiosk.sh; sh -n leo-kiosk/run.sh; PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/integration/test_staged_install.py`.

### parent-72 (frontend)
- **ID:** parent-72
- **Type:** frontend
- **Precedence:** P0
- **Difficulty:** hard
- **Depends on:** parent-46, parent-43, parent-42, parent-44, parent-64, parent-65, parent-28, parent-69
- **Model:** deepseek/deepseek-v4-flash
- **Summary:** Assemble real services and GTK routes in the application entry point
- **Details:** Complete application.py composition only: storage/bootstrap/import, owned sessions/input, navigation, all views, libnm/agent and portal services. Use real adapters in production, lazy optional network/browser initialization and deterministic teardown; missing NM/WebKit must not crash child home or review. Refresh views after commits and guard partially initialized shutdown. Do not reimplement service logic in widgets. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/ui/test_application_wiring.py; python3 leo-kiosk/launcher.py in nested Cage`.

### parent-73 (other)
- **ID:** parent-73
- **Type:** other
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-18, parent-19, parent-20
- **Model:** openai/gpt-6.1-sol
- **Summary:** Verify catalog/review/home invariants with stateful tests
- **Details:** Add Hypothesis/reference-model command sequences for import/test/review/select/replace/move/unselect/delete/reimport and injected SQL failures. Assert exactly nine slots, no duplicate/tenth selections, derived statuses, tombstone persistence, original source preservation and all-or-nothing writes. Keep tests deterministic with temporary SQLite only. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/integration/test_catalog_properties.py`.

### parent-74 (other)
- **ID:** parent-74
- **Type:** other
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-21, parent-23, parent-30, parent-28
- **Model:** openai/gpt-6.1-sol
- **Summary:** Verify noisy physical-input and timing behavior
- **Details:** Add property tests for arbitrary volume/nonvolume streams, releases/repeats, wrong suffixes, gap/window boundaries, cooldown, route resets and suspend/hotplug. Use fake clock/fds and sanitized volume-only target fixtures; prove old DU never matches and a consumed event cannot emit another action. No live keyboard capture in CI. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/unit/test_gesture_properties.py`.

### parent-75 (other)
- **ID:** parent-75
- **Type:** other
- **Precedence:** P0
- **Difficulty:** hard
- **Depends on:** parent-27, parent-28, parent-31, parent-45, parent-36
- **Model:** openai/gpt-6.1-sol
- **Summary:** Verify owned-process cleanup and every return role
- **Details:** Add controlled subprocess fixtures for natural/immediate exit, missing executable, ignored TERM, descendants and profile locks; simulate duplicate/stale timeout/gesture callbacks. Assert one outcome, no newer/unrelated process signals, correct child/editor return, tested semantics and profile cleanup. Tests may signal only their own fixture groups. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/integration/test_sessions.py`.

### parent-76 (other)
- **ID:** parent-76
- **Type:** other
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-1, parent-47
- **Model:** openai/gpt-6.1-sol
- **Summary:** Create an isolated NetworkManager D-Bus fixture
- **Details:** Add tests/fixtures/networkmanager.py using python-dbusmock/private test bus and explicit injection into the GI adapter. Model required NM devices/APs/profiles/permissions/secrets/connectivity methods/properties; ensure teardown. Never redirect tests to the host system bus or use real credentials. Keep fixture extensible rather than mocking every adapter method. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/integration/test_nm_fixture.py`.

### parent-77 (other)
- **ID:** parent-77
- **Type:** other
- **Precedence:** P0
- **Difficulty:** hard
- **Depends on:** parent-76, parent-65, parent-51, parent-53, parent-55
- **Model:** openai/gpt-6.1-sol
- **Summary:** Exercise the real NM adapter against isolated D-Bus scenarios
- **Details:** Add integration tests for scan/AP-security grouping, saved/new activation, secret retry/cancel, permission denial, late cancel, daemon restart and portal/full/unknown/disabled-probe transitions. Assert no stale snapshots, leaked prompts/subscriptions or unauthorized system-profile mutations. Record differences unsupported by dbusmock for mandatory target tests rather than silently bypassing them. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/integration/test_networkmanager.py`.

### parent-78 (other)
- **ID:** parent-78
- **Type:** other
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-1
- **Model:** openai/gpt-6.1-sol
- **Summary:** Create local redirected captive-portal fixtures
- **Details:** Add tests/fixtures/portal_server.py with two local origins, HTTP login redirect, text/password inputs, iframe, popup/download/custom-scheme cases and self-signed TLS failure. Expose fake online transition through the test backend; keep credentials synthetic and ports temporary. Fixture startup/teardown must not reconfigure DNS or the host network. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/integration/test_portal_fixture.py`.

### parent-79 (other)
- **ID:** parent-79
- **Type:** other
- **Precedence:** P0
- **Difficulty:** hard
- **Depends on:** parent-78, parent-64, parent-77
- **Model:** openai/gpt-6.1-sol
- **Summary:** Verify portal keyboard, isolation and lifecycle under Wayland
- **Details:** Use the local fixture to test production WebKit touch adapter, redirects/password/iframe focus, safe popup handling, TLS rejection, single-flight checks, no form reload, cancellation and network changes. Assert contexts share no child/review Firefox state and stale checks cannot approve new networks. Mark display/Wayland requirements honestly; physical touch remains a separate gate. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest -m wayland leo-kiosk/tests/ui/test_portal_integration.py`.

### parent-80 (other)
- **ID:** parent-80
- **Type:** other
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-72, parent-73, parent-74
- **Model:** openai/gpt-6.1-sol
- **Summary:** Verify complete parent/review UI workflows with fake devices
- **Details:** Add display-marked smoke tests for nine grey tiles/three labels, row trial/editor return, rating null/0/100, Keep/Select/replacement/Delete/Ok/Next, dirty confirmation, queue end and reboot persistence. Include credentials UI state and action-bar visibility with keyboard open using fake network/process backends; no public game fetches. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest -m display leo-kiosk/tests/ui/test_parent_workflows.py`.

### parent-81 (other)
- **ID:** parent-81
- **Type:** other
- **Precedence:** P0
- **Difficulty:** hard
- **Depends on:** parent-72, parent-66, parent-67, parent-68, parent-71, parent-75, parent-77, parent-79, parent-80
- **Model:** openai/gpt-6.1-sol
- **Summary:** Review browser, process, input and privilege boundaries
- **Details:** Write docs/parent-mode/security-review.md auditing untrusted names/SSIDs/URLs, argv, file ownership, Firefox profiles/policies, portal sandbox/TLS, secret/log handling and polkit defaults/new grants. Exercise external links/downloads/dialogs and malicious catalog fixtures. Record gesture-only access/input-group/browser limitations; unresolved root wildcard, injection or sandbox bypass blocks release. Verify: `Run the named negative-input/integration suites; record target permission checks and manual browser escape attempts without exposing secrets`.

### parent-82 (other)
- **ID:** parent-82
- **Type:** other
- **Precedence:** P0
- **Difficulty:** hard
- **Depends on:** parent-81, parent-80, parent-75
- **Model:** openai/gpt-6.1-sol
- **Summary:** Accept physical gestures and game curation on Surface Go
- **Details:** Record docs/parent-mode/hardware-review-acceptance.md with versions and measured offline boot, matched grids, gestures while GTK/Firefox is focused, landscape/portrait/blocked/broken trials, touch edits, all CTAs/slot changes, queue end, crash/timeout, hotplug, sleep and reboot persistence. Verify Exit stays in kiosk and old DU/five-tap exits are gone. Missing critical rows block release. Verify: `Run architecture section 12 tablet review/session matrix after cold boot; record pass/fail evidence without personal content`.

### parent-83 (other)
- **ID:** parent-83
- **Type:** other
- **Precedence:** P0
- **Difficulty:** hard
- **Depends on:** parent-81, parent-58, parent-79, parent-71
- **Model:** openai/gpt-6.1-sol
- **Summary:** Accept restricted Wi-Fi and touch-only captive login on Surface Go
- **Details:** Record docs/parent-mode/hardware-network-acceptance.md with open/WPA2/supported WPA3, wrong password, saved reconnect/forget permissions, rfkill/service failure, network switch and touch-only portal flows including iframe fields. Check hidden networks if the optional form is implemented. Verify cookie/credential separation, online uncertainty handling and administrator-approved networking rollback with physical recovery available. Verify: `Run architecture section 12 networking/portal matrix as leo; record installed versions, outcomes and rollback proof with no real credentials`.

### parent-84 (other)
- **ID:** parent-84
- **Type:** other
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-72, parent-71
- **Model:** openai/gpt-6.1-sol
- **Summary:** Update parent instructions and administrator recovery runbooks
- **Details:** Update README.md and docs/parent-mode/user-guide.md/operations.md with exact gestures, Exit semantics, statuses, CTA/slot behavior, ratings, Wi-Fi support/limitations, portal controls, backups/logs and restore/recovery. Remove obsolete current-behavior claims only when implementation exists. Document discovery-versus-playback evidence and no guaranteed child web filtering; reconcile document links and new paths. Verify: `Check local Markdown links; have a second reader follow a review/select/login and stopped-app backup/restore walkthrough`.

### parent-85 (other)
- **ID:** parent-85
- **Type:** other
- **Precedence:** P0
- **Difficulty:** medium
- **Depends on:** parent-82, parent-83, parent-84
- **Model:** openai/gpt-6.1-sol
- **Summary:** Publish an administrator-approved staged deployment and rollback checklist
- **Details:** Write docs/parent-mode/release-checklist.md covering backups of app/config/SQLite/network profiles, staged asset installation, cold-boot child/parent/review/network checks and explicit rollback triggers. Rehearse restoration with the tablet locally recoverable; keep prior artifacts and parent-data export. Do not perform root/network actions without the administrator approval required by the runbook. Verify: `Record a staged install and rollback rehearsal, then rerun cold-boot acceptance; no release on unresolved critical gates`.

### parent-86 (other)
- **ID:** parent-86
- **Type:** other
- **Precedence:** P2
- **Difficulty:** easy
- **Depends on:** parent-20, parent-69, parent-81
- **Model:** openai/gpt-6.1-sol
- **Summary:** Add optional read-only sanitized support diagnostics
- **Details:** Add tools/leo_diagnostics.py reporting versions/schema/catalog checksum, slot invariants, abandoned-session summary and network capability availability. Default read-only; optional explicit SQLite backup reuses the safe backup API. Exclude secrets, browser profiles/history and full URLs; never auto-repair data, change Wi-Fi or signal processes. Verify: `PYTHONPATH=leo-kiosk python3 -m pytest leo-kiosk/tests/unit/test_support_diagnostics.py; python3 tools/leo_diagnostics.py --help`.

DEEEPR:PLAN_READY
