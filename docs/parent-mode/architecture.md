# Parent mode, game curation, and Wi-Fi architecture

Status: implementation specification; no application behavior has been changed.

## 1. Scope and decisions

Build a parent area into the existing Python/GTK3 tablet launcher. Keep Cage, greetd, the native application tiles, and the existing child-facing layout. Do not introduce a web server, JavaScript frontend, root-running UI, or a second network manager.

Deliverables:

1. A nine-tile, grey parent menu opened by volume **Up, Down, Down**.
2. A game catalog, trial player, review editor, and persistent nine-slot home selection.
3. A touch-friendly Wi-Fi screen using **NetworkManager/libnm with iwd as the supplicant backend**.
4. An isolated captive-portal browser, recovery behavior, automated tests, and an administrator deployment/rollback procedure.

### Product interpretations adopted for this specification

| Ambiguity | Default decision |
|---|---|
| “Only 2 tiles” followed by three names | Three active tiles: **Review**, **Wifi**, **Exit**; six disabled, unlabeled grey tiles. |
| Parent menu tile count | Nine, in the same three-by-three geometry as the home screen. |
| Meaning of Exit | Leave parent mode and return to the child home screen; **do not exit Cage, log out, or power off**. |
| Old invisible five-tap exit corner | Remove from the child interface. Retain administrator recovery through SSH/text console, not an invisible child-accessible exit. |
| Catalog content | Import all existing entries for preservation. Review defaults to **games only**; videos have a separate optional filter and are not eligible for game slots in this release. |
| Existing home activities | Preserve all nine existing tiles initially. Selecting a game replaces one chosen slot, including a legacy activity. Never silently remove an activity. |
| “Selected” | Occupies exactly one of the nine home positions, rather than merely being a favorite. |
| Return gesture | **Down, Up** is retained for exiting a game under review (back to its editor). **Down, Down, Up** handles all other returns (child playback to child home, parent surfaces to child home). The two sets must never be enabled simultaneously; the recognizer swaps context-owned pattern sets on route change. |
| “Keep/delete/select” versus the three bottom CTAs | Keep/Select is a draft choice in the editor; **Delete**, **Ok**, **Ok and see next** are the three bottom buttons. Delete is the discard choice. |
| Rating | Optional until supplied; otherwise an integer **0–100**, inclusive. Null means unrated; zero is a real rating. |
| Delete | Soft-delete from the review queue, removing its home assignment in the same transaction. Keep a tombstone so reimport does not resurrect it. |
| Parent gesture security | Convenience barrier, not authentication or a parental-control security boundary. A child can learn it. PIN authentication is a later feature, not implicitly promised. |

These defaults are explicit so a developer does not have to invent product behavior. Changing them requires updating the affected tests and this specification.

## 2. What exists today

Inspected files:

- `app/launcher.py`: one GTK3 window, nine configurable tiles, `subprocess.Popen`, a time limit, and a hidden parent-exit corner.
- `app/backwatch.py`: raw Linux input parsing; watches every input device, recognizes Down then Up, and kills the group in `.app-pid`.
- `app/run.sh`: starts backwatch separately, then execs the launcher.
- `config/tiles.json`: nine native/local activities and their existing time limits.
- `install-kiosk.sh`: Arch package installation, copying individual files, input-group membership, and greetd/Cage setup.
- `README.md`: reports setup using `nmtui`; this suggests NetworkManager was used, but does **not** verify the tablet's current networking backend.
- `web-games.json`: already saved at the project root. Fourteen provider groups, **109 items: 93 labeled game, 16 video**. It is an input catalog, not proof that every entry is an actual, playable single game.

Existing defects to fix within this work:

- The watcher sends signals itself and trusts a shared PID file; stale PID reuse and missing launch context are avoidable.
- Delayed launcher callbacks operate on `self.proc`; after a new launch they could act on the wrong application.
- The watcher logs all key codes on all input devices, more information than this feature needs.
- The launcher cannot distinguish child playback, review trials, and parent navigation.
- Hidden GTK focus alone cannot receive volume events while Firefox is foregrounded on Wayland.
- The installer would not copy a new multi-module application or the catalog today.

Do not assert a live-device state until the platform acceptance spike has run on the Surface Go.

## 3. Architecture

```text
root / administrator provisioned
  greetd -> leo session -> Cage
                           |
                           +-- launcher.py (one surviving GTK process)
                                |
                                +-- Gtk.Stack / navigation controller
                                |    +-- ChildHome (9 slots)
                                |    +-- ParentHome (9 grey tiles)
                                |    +-- ReviewList
                                |    +-- ReviewEditor
                                |    +-- Wifi / Credentials
                                |    +-- PortalView (embedded WebKitGTK)
                                |
                                +-- InputMonitor: python-evdev + pyudev + GLib
                                |    -> GestureRecognizer -> controller actions
                                |
                                +-- CatalogService / ReviewService / HomeService
                                |    -> sqlite3 repositories -> local SQLite file
                                |
                                +-- AppSessionManager
                                |    -> dedicated Firefox process group for a game
                                |    -> existing trusted native activities
                                |
                                +-- WifiService -> libnm (system D-Bus)
                                                       |
                                                       +-- NetworkManager
                                                            +-- iwd (Wi-Fi association)
                                                            +-- DHCP / routes / DNS
                                                            +-- connectivity probing

Portal: WebKitGTK isolated network context -> HTTP login redirect -> HTTPS login
```

### Ownership rules

- One process owns UI navigation, active playback, game persistence, and interpretation of input actions.
- `InputMonitor` is an in-process service attached to the GLib event loop. It continues receiving raw events while the GTK window is hidden. It never kills a PID or reads `.app-pid`.
- Only `AppSessionManager` starts or terminates application processes. At most one external activity is active.
- No game JavaScript can call launcher methods. Games run in external Firefox, not a privileged webview.
- NetworkManager owns IP configuration. iwd handles Wi-Fi association/authentication underneath it. Do not run standalone iwd DHCP, dhcpcd, or a competing manager on the same interface.
- The application never calls sudo, edits root configuration, or embeds an administrator password. System changes are an explicit administrator installation step.

### Modules and allowed dependencies

```text
app/
  launcher.py                     # small application entry point
  leo_kiosk/
    application.py                # construction, GLib lifecycle, cleanup
    domain/
      models.py                   # enums, immutable DTOs, validation
      gestures.py                 # pure state machine, no GI/Linux imports
      review_queue.py             # frozen queue and next-item rules
    services/
      navigation.py               # explicit route + parent-session state
      catalog.py                  # imports and validation orchestration
      reviews.py                  # draft/save/delete/selection transactions
      home.py                     # nine slots and trusted legacy conversion
      sessions.py                 # launch tokens, timers, termination
      wifi.py                     # networking state machine
    storage/
      database.py                 # sqlite3 connection and migrations
      migrations/                 # numbered SQL migrations
      repositories.py             # parameterized SQL only
    adapters/
      input.py                    # evdev + udev fd integration
      firefox.py                  # arguments and profile lifecycle
      legacy_apps.py              # trusted cmd from local configuration only
      networkmanager.py           # NM.Client and async callbacks
      secret_agent.py             # NM.SecretAgentOld subclass
    ui/
      window.py                   # Gtk.Stack and route rendering
      tile_grid.py                # shared geometry; separate child/parent styling
      review_list.py
      review_editor.py
      wifi.py
      portal.py                   # WebKit2 4.1, no launcher JS bridge
      keyboard.py                 # GTK keyboard + input target adapters
      styles.css
  catalog/                        # imported build-time assets
  tests/{unit,integration,ui}/
  run.sh
  install-kiosk.sh
```

Dependency direction: `ui -> services -> domain + repositories/adapters`. Domain code must import neither GTK nor NetworkManager. UI widgets do not issue SQL, terminate processes, or execute network commands. Use plain dataclasses and `typing.Protocol` interfaces, not a dependency-injection framework.

## 4. Library and platform choices

“Backend” below means local domain/storage/platform services, not an HTTP backend.

| Purpose | Selection | Reason / rejected alternative |
|---|---|---|
| Native interface | Existing **GTK3 + PyGObject**, `Gtk.Stack`, `Gtk.ListBox`, `Gtk.Grid` | Fits the current app. 109 records do not justify a frontend rewrite or a virtualization framework. Defer GTK4 migration. |
| Async/event loop | **GLib/Gio**, `Gio.Cancellable`, async libnm calls | One event loop. No asyncio/GLib integration layer; never block GTK with network waits or `subprocess.run`. |
| Domain objects | Python **dataclasses**, `enum.IntEnum`, `typing.Protocol` | Typed small local application without an ORM/model framework. |
| Storage | Python standard-library **sqlite3** | Transactions for home-slot selection and durable review state; no SQLAlchemy or server database needed. |
| Catalog schemas | **jsonschema**, Draft 2020-12 | Validate the supplied and normalized JSON forms and give errors with file/item locations. |
| Linux volume buttons | **python-evdev** | Avoid hard-coded `struct input_event` layout and manual key/event parsing. |
| Device hotplug | **pyudev** | Filter and monitor `/dev/input` additions/removals without startup-only enumeration. |
| Wi-Fi | **libnm 1.0** through PyGObject (`gi.require_version('NM', '1.0')`) | NetworkManager's supported API, async events, secret-agent integration and connectivity states. Do not parse localized `nmcli` output or build raw iwd D-Bus handling. |
| Wi-Fi supplicant | **iwd** as NetworkManager backend | Meets the iwd requirement while retaining NetworkManager's IP/probe management. Python stdlib has no Wi-Fi/captive-portal management API. |
| Wi-Fi authorization | Existing system **polkit** | Narrow, active-local-session permissions; no root-running helper or general shell bridge. |
| Game browser | Existing **Firefox**, native Wayland, dedicated profile | Preserve web-game compatibility and browser sandbox. Do not replace it with WebKit for games without a new compatibility study. |
| Portal browser only | **WebKitGTK 4.1**, `WebKit2` GIR, sandboxed ephemeral context | Embed inside parent UI, keep visible Back/Reload/Done controls, cookies separate from child Firefox. Avoid a general desktop browser escaping kiosk navigation. |
| Touch text entry | Reusable **GTK keyboard** with Gtk.Editable and WebKit editing adapters | Cage support for virtual keyboards alone is insufficient for standard layer-shell keyboards. Do not assume Onboard/wvkbd/squeekboard works in this session. Prove portal editing on hardware before completing the feature. |
| Tests | **pytest**, **Hypothesis**, `unittest.mock`; **python-dbusmock** for NM integration | Pure state-machine/property tests plus real NM D-Bus shape simulation. |
| UI smoke tests | pytest + GI under nested/headless **Cage/Weston** as available | Xvfb can test GTK widget logic but does not prove Wayland focus, raw buttons, browser presentation, or portal usability. |
| Code checks | **Ruff**; type-check pure domain/services with **mypy** | GI-generated types are incomplete; isolate adapters rather than inventing a type system for every GI object. |

Candidate Arch runtime packages, to validate against the target package repositories: `gtk3`, `python-gobject`, `python-evdev`, `python-pyudev`, `python-jsonschema`, `networkmanager`, `libnm`, `iwd`, `polkit`, `webkit2gtk-4.1`, `firefox`; SQLite is accessed through the system Python build. Keep Cage/greetd/audio dependencies already in the installer. Test dependencies are not installed onto the child's production session by default.

### Upstream facts checked while making this design

- NetworkManager configuration documents `wifi.backend=iwd`, the configurable iwd autoconnect policy, and optional connectivity checks. A system with no probe URI may have no usable portal detection.
- libnm exposes asynchronous activate/deactivate/connectivity operations and a subclassable secret-agent API.
- Upstream Cage source exposes virtual-keyboard support, but this does not establish support for the layer-shell and input-method protocols used by off-the-shelf on-screen keyboards; the installed build still needs measurement.
- WebKitGTK 4.1 exposes an ephemeral WebContext and editing-command APIs. Focus retention, command support, cross-origin iframe inputs, and password entry remain hardware/browser acceptance gates, not assumed capabilities.

Confidence (1 uncertain, 5 strongly supported): retain GTK/SQLite/Firefox **5**; libnm + iwd design **4** pending target inspection; touch-only captive-portal keyboard **3** until the platform spike passes. No promise that every captive portal, enterprise network, DRM video, or third-party game will work.

## 5. Catalog files, provenance, and import

### SQLite authority and flexible discovery inputs

SQLite is the authoritative catalog/review store. The owner explicitly permits rearranging `web-games.json` or deleting it after its data is migrated. Its current grouped layout and original six-key proposal are **not fixed contracts**. Do not duplicate mutable parent decisions back into JSON.

Keep the current file only until a verified, restart-persistent import and a fresh-install bootstrap are available. Record useful source identities, checksums, unknown metadata, evidence and exclusions in SQLite/bootstrap metadata; permanent byte-for-byte retention of that filename is not required. When removing it, update references and keep small parser fixtures rather than making tests depend on its old shape.

Use a versioned `catalog/bootstrap.json` plus validation schema to seed fresh installations without overwriting existing SQLite reviews. The bootstrap is a replaceable deployment asset, not the live datastore; fields may follow the domain DTOs rather than the original display/export format. Validate it independently of the optional original file.

Domain contracts retained regardless of import layout:

- Media types: **0 = other, 1 = video, 2 = game**; these are application enums, not browser MIME types.
- Unknown dimensions are nullable; known sizes are a positive integer pair with explicit `unknown/design/iframe/popup/inferred` evidence. Popup/inferred values are not measured game resolutions.
- Orientation is explicit `unknown/landscape/portrait/square`. There is no need for false/zero compatibility placeholders now that the source format is unconstrained.
- Stable source IDs and original/parent names remain separate. Source URL, launch override and provenance survive reformatting, import and restart.
- Preserve arbitrary JSON-object source metadata in `source_metadata_json` without promoting it to review status or executable commands.

### Discovery hygiene

The current 109 entries include a Starfall section URL, query-based Sesame game links and metadata inferred across games. Audit available records and preserve useful provenance, excluding only confirmed section/hub links from the playable queue. A `/games?id=...` path may identify an individual game and must not be discarded just for its path/name. Do not hard-code either the current input count or an expected eligible count of 93.

- Initial HTTP 200 proves neither a single-game page nor successful playback. Record discovered/checked evidence separately from parent status.
- Keep Gulli geo-blocking and per-item portrait/landscape metadata. Its launcher popup sizes are **not** game-canvas resolutions.
- Lumni dimensions must be checked per item; do not copy one 708×600 sample to every game.
- Keep videos for later inspection but hide them under the default game-only filter. A separate video viewer is not part of this release.
- Name strings in JSON and SSIDs are untrusted plain text. Never insert them as GTK markup or shell commands.

### Stable identity and validation

- Stable ID: UUIDv5 over `provider_id + '\n' + canonical_source_url` using a checked-in namespace UUID.
- Conservative URL normalization: lowercase scheme/host, normalize default ports; preserve query, path case, fragments, and unknown parameters. A query or fragment may identify the game. Keep original source URL and separately editable launch URL.
- Only `http` and `https` URLs are accepted. Reject userinfo, control characters, empty hosts, and shell-like schemes. Do not automatically fetch untrusted URLs during import. Manual trials may legitimately redirect or contact third-party hosts.
- Dedupe exact canonical provider/URL identities. Do not merge different games by title or guessed redirect equivalence.
- Import a complete file atomically after validation; show a useful error and leave the old catalog unchanged on failure.
- Reimport may update source metadata, but never overwrite parent rename/rating, resurrect tombstones, move slots, or reset testing/review history. A removed source entry stays locally available until the parent decides otherwise.
- Import reports list added/updated/unchanged/invalid/excluded entries and the source checksum.

## 6. Persistence model

Use `${XDG_DATA_HOME:-~/.local/share}/leo-kiosk/catalog.sqlite3`; config and discovery assets stay outside this mutable file. Browser caches use `XDG_CACHE_HOME`, private runtime artifacts use `XDG_RUNTIME_DIR`. Directories containing private data are mode 0700.

Core tables:

| Table | Essential columns |
|---|---|
| `schema_migrations` | version, checksum, applied_at |
| `providers` | id, name, website_url |
| `catalog_imports` | id, source_checksum, imported_at, report_json |
| `games` | id, provider_id, canonical_source_url, launch_url, source_name, parent_name nullable, media_type, source_metadata_json, tested_at nullable, reviewed_at nullable, rating nullable, deleted_at nullable, revision |
| `home_slots` | position integer PK 1–9, game_id nullable UNIQUE FK, legacy_tile_json nullable |
| `launch_sessions` | id UUID, game_id nullable, slot nullable, role, started_at nullable, ended_at nullable, outcome nullable (requires ended_at), failure_reason nullable |
| `review_events` | id, game_id, event_kind, timestamp, change_json; no browser passwords or web history |

Database constraints:

- `rating IS NULL OR rating BETWEEN 0 AND 100`, and enforce integer type in validation/constraint.
- Unique `(provider_id, canonical_source_url)`.
- `home_slots` allows either a game, a trusted legacy tile, or an empty slot, never both game and legacy content. Exactly nine slot rows are seeded and are updated, never deleted by application code (enforced by a `BEFORE DELETE` trigger, since foreign keys alone cannot prevent row deletion). A set outcome requires `ended_at`; recovery may finish a session without an outcome.
- Only a nondeleted reviewed **game** may occupy a game slot. Enforce cross-table invariants in one domain transaction and, where practical, constraints/triggers; test invalid repository writes.
- Selected games occupy one slot each; at most nine can be selected. There can be fewer than nine selected games because other slots can still hold native activities or be empty.
- Do not store `selected` as a second independent boolean: derive it from `home_slots` to prevent drift.

Connection policy: foreign keys on, WAL mode, finite busy timeout, parameterized SQL, deliberate transaction scopes. Use UTC timestamps for persisted history, `time.monotonic()` for gesture windows, and Linux `time.clock_gettime(time.CLOCK_BOOTTIME)` for playback deadlines so suspended time counts without depending on wall-clock corrections. Use SQLite backup API before schema upgrades; fail closed with a parent-visible error if migration fails. One main-thread connection owns small writes; parse files off-thread if necessary and return immutable results through GLib. Never share a sqlite connection across threads.

### Status derivation

Precedence for active records:

```text
home slot exists -> selected
else reviewed_at exists -> reviewed
else tested_at exists -> tested
else -> new
```

- A successfully spawned browser trial sets `tested_at` for a previously new game. It means “a trial was attempted,” **not** “game loaded successfully.” Store browser startup/exit outcomes separately.
- Failed process spawn does not mark the item tested; show retry/return actions.
- Re-testing a reviewed or selected game does not downgrade its displayed status.
- Any Ok save sets `reviewed_at`. Selected implies reviewed. A saved review is allowed after a failed/blocked trial if the parent explicitly saves it; the failure remains visible.
- Delete soft-deletes any state and removes its slot in the same transaction. Deleted is an exclusion/archive state, not a fifth primary status badge.

### Atomic review save

`save_review(game_id, expected_revision, name, rating, selection_intent, target_slot)`:

1. Validate name, integer/null rating, game eligibility, revision, and slot assignment.
2. In one transaction save parent name/rating/review timestamp and increment revision.
3. If keeping without selection, remove this game's assignment if it had one; leave that slot empty.
4. If selecting, keep its existing slot unless a different slot is explicitly chosen. For a new selection require the parent to choose one of positions 1–9; show what will be replaced.
5. Replace the target game or native activity only after explicit confirmation. A displaced game remains reviewed, not deleted. Moving a selected game clears its old slot; do not silently swap two entries.
6. Append the audit event and commit; refresh both home and list from committed data.
7. On failure roll back everything, keep the editor draft, and offer Retry. Never navigate to next after a failed save.

`delete_game` similarly uses one transaction. A destructive confirmation names the item and any affected home position. Tombstones retain review metadata for support/export; a read-only Deleted filter plus explicit Restore may be added, but restoration must never auto-select it.

## 7. Navigation and volume gestures

### Routes and session context

Top-level routes: `CHILD_HOME`, `PARENT_HOME`, `REVIEW_LIST`, `REVIEW_TRIAL`, `REVIEW_EDITOR`, `WIFI`, `PORTAL`, `CHILD_ACTIVITY`.

A parent session stays active across Review, Wifi, trial playback, and portal navigation until Exit is chosen. A launch session records its role and return context; closing a process is not enough to decide where to go.

| Current context | Up, Down, Down | Down, Down, Up | Down, Up |
|---|---|---|---|
| Child home | Parent home | No-op | No-op |
| Child game/native activity | Stop owned activity, then parent home | Stop activity, then child home | No-op |
| Parent home | No-op | Child home | No-op |
| Review list | Parent home | Parent home | No-op |
| Review trial | Stop trial, then parent home | No-op (geometrically the trailing D,U completes the short match; see below) | Stop trial, then review editor for that exact game |
| Review editor | Parent home, with unsaved-change confirmation | Review list, with unsaved-change confirmation | No-op |
| Wifi | Parent home; cancel pending UI work safely | Parent home; cancel pending UI work safely | No-op |
| Portal | Close portal, then parent home | Close portal, then Wifi | No-op |

Only one pattern set is enabled at a time. The default set (Up/Down/Down and Down/Down/Up) is active on child, parent, list, editor, Wifi, and portal surfaces. The review-trial set (Down/Up) is active only while a game is running for review, because the short return would otherwise swallow ordinary volume adjustments on every other surface.

Natural browser exit, child timeout, review timeout, and browser crash follow the recorded origin: child activity -> home; review trial -> editor with an outcome banner. Never lose which game was under review. Parent trials use a configurable safety timeout (default 30 minutes), not the child's per-slot time limit.

### Recognizer contract

- Accept key-down (`EV_KEY`, value 1) for volume up/down only. Ignore releases, repeats (value 2), unrelated keys and power events.
- Recognize exactly `[UP, DOWN, DOWN]` and `[DOWN, DOWN, UP]` on child/parent/list/editor/Wifi/portal surfaces, and `[DOWN, UP]` during a review trial, using a rolling buffer and `time.monotonic()`. Pattern sets are context-owned and swapped on route change; they are geometrically compatible (Down/Up diverges from Down/Down/Up at the second key) but must never be enabled simultaneously outside trial playback, because the short return would swallow ordinary volume adjustments.
- Defaults: no gap greater than 1.0 second, complete sequence within 2.0 seconds. Both values are configuration, not sprinkled constants.
- After a match consume the entire buffer and apply a 500 ms cooldown. Reset on route changes, suspend/resume, device removal, and sequence timeout.
- Wrong sequences keep only the valid suffix needed for a new match; one press cannot participate in two emitted actions.
- Select the tested physical volume-button source. If hardware exposes duplicate devices, choose a stable udev identity; never globally debounce fast distinct taps into one tap.
- Ordinary volume events are not grabbed or replayed. Gestures may change volume as taps occur. Preserve any existing audio-control path; check target behavior. Restoring audio or swallowing partial sequences is a separate product choice, not hidden behavior.
- Device permissions are read-only access to required input devices, not an evdev grab. Do not log general keyboard events. Prefer a targeted udev rule over broad `input` membership once the device is identified; the initial prototype may retain the existing group with a documented risk.

## 8. Parent UI and review interaction

### Parent menu

Reuse the home grid's margins, spacing, row/column expansion and tile size. All nine tiles are grey; only the first three contain the labels Review, Wifi, Exit. The remaining six have no click handler and are not keyboard focus stops. Add a visible “Parent” title; do not rely on grey alone to communicate mode.

### Review list

- One touch row per eligible item with display name and one of **new / tested / reviewed / selected** as text badges.
- Secondary information: provider, optional rating, orientation/size evidence, and last launch problem. Never imply “selected” means already loaded successfully.
- Persistent filters: status, provider, search; default content type games. Show `Selected games: N/9` separately from `Occupied home slots: M/9`.
- Default stable order: provider name, source name, ID. Search and sort do not change item identity.
- Row tap launches a trial; it does not directly approve or select the game. A secondary “Edit review” action can reopen existing metadata without another launch.
- Disable repeated launch taps while one launch request is pending; show immediate loading feedback. Preserve scroll position and filters on return.
- Freeze the visible queue of IDs on row activation for “Ok and see next.” It includes the tapped item and later eligible items in that displayed order; new imports do not reshuffle an active review session.

### Trial playback

Open the actual single-game URL in Firefox kiosk mode. Prefer a provider's actual playable landing page rather than a fragile internal build hash unless the direct URL is already known and deliberately curated. Show a brief parent instruction before launch: “Return: Volume Down, Up.”

On return persist a session outcome, then display the editor. Network failure, unsupported graphics, ads, account gates and geo-blocks are review evidence, not reasons to auto-approve. Browser startup cannot measure actual canvas resolution; show source dimensions with evidence labels until a parent verifies them.

### Review editor

Fields:

- Display name: editable, trimmed, 1–80 Unicode characters, original title visible; no markup.
- Rating: optional 0–100% slider plus integer numeric entry and small +/- controls. Keep zero distinct from unrated. Validate before save.
- Choice: **Keep in library** or **Select for home**. Previously selected games default to Select and their current position.
- Slot picker when selecting: nine numbered positions, occupant names and replacement confirmation; do not silently use “first empty” or remove the lowest-rated game.
- Source URL/provider, status, last trial outcome and resolution-evidence summary are read-only.

Bottom action bar, always reachable even with keyboard open:

| CTA | Behavior |
|---|---|
| **Delete** | Confirm, soft-delete and unselect atomically, then return to the list at the nearest remaining row. Does not save draft name/rating. |
| **Ok** | Save metadata and Keep/Select decision atomically, then return to the list. |
| **Ok and see next** | Save the same way, then launch the next eligible item from the frozen queue. |

Next rules: skip deleted/ineligible IDs, do not loop, do not reorder after ratings/names change, and show “Review queue complete” when no next item exists. Disable/rename the next CTA appropriately at queue end. If the next launch fails, show that item's retry/error state, not the previous editor. Explicitly backing away with unsaved fields asks Save / Discard / Cancel; Discard affects only draft edits, not the recorded trial.

### Child home

Nine positions remain stable. Game selections replace slots individually. Keep a nine-slot grid even when slots are empty; empty tiles are disabled and never expose parent actions. Legacy activities retain their current labels, colors and time limits. New game tiles receive deterministic colors and the parent name, with label wrapping/ellipsizing rather than tiny text. New game limits default to 20 minutes and can use a local config override; do not infer limits from rating.

## 9. Process lifecycle and browser isolation

- Spawn with an argument array, **never shell=True**. Build a Firefox command using `--no-remote`, `--new-instance`, `--profile`, `--kiosk`, and a validated URL. Confirm the supported argument behavior on the installed Firefox version.
- Set native Wayland behavior for the kiosk Firefox environment as needed on the target. Do not disable browser sandboxing or TLS verification.
- Each launch receives a UUID token, captured process object, PGID, role, origin, timer IDs, suspend-aware boot-clock deadline, and phase (`starting/running/stopping/finished`).
- Every timer/exit callback checks that token. Cancel callbacks on completion. Send SIGTERM to the owned group and SIGKILL after a bounded grace period (default 3 seconds); callbacks never read “whichever process is current.”
- Browser root-process exit is not proof all children stopped; verify cleanup of the owned process group. A supervisor/systemd-scope follow-up is warranted only if target tests demonstrate escaped descendants.
- Hide the launcher only once launch ownership is recorded and the application has started. Present it again on every exit/failure path. On Wayland use the compositor's normal focus behavior; do not assume `present()` overrides all focus rules.
- Review trials use a fresh private per-trial Firefox profile, cleaned only after browser shutdown. Child web games use a distinct child-only profile so game progress can survive sessions. Parent portal cookies/passwords never enter either profile. Do not use the administrator's/default Firefox profile.
- Kiosk flags do not turn arbitrary sites into a complete security sandbox: browser navigation, links, downloads and dialogs need explicit tests and preference/policy restrictions. Block downloads/external protocol handlers/permission prompts as appropriate without breaking games. Do not force a global same-origin allowlist that breaks legitimate game CDNs; network-level child filtering is a separate feature.
- Game catalog entries cannot contain commands or executable arguments. Native activity commands come only from the administrator-owned legacy configuration.
- Persist session records but never kill an old PID from disk on startup. Detect abandoned sessions, offer the relevant review editor, and clear stale `.app-pid` after migration. Recovery decisions use owned current processes or validated service ownership, not PID number reuse.
- Integrate input monitoring into the launcher and retire `backwatch.py` from production `run.sh`. Keep the old file only as a documented migration artifact until cleanup.

## 10. Wi-Fi and captive portals

### Correct stack and provisioning

The Python standard library does not implement Wi-Fi scanning, WPA authentication or captive-portal workflows. The standard platform library here is **libnm**, using NetworkManager's system D-Bus service.

Administrator-provisioned configuration, with backups and rollback:

```ini
# /etc/NetworkManager/conf.d/leo-iwd.conf
[device]
wifi.backend=iwd
wifi.iwd.autoconnect=false
```

`wifi.iwd.autoconnect=false` makes NetworkManager own the autoconnect decision rather than having two independent policies. Check support and migration behavior against the installed NM version before deployment.

```ini
# /etc/iwd/main.conf (merge, do not overwrite unrelated existing settings)
[General]
EnableNetworkConfiguration=false
```

NetworkManager must be the sole DHCP/routing owner. Audit DNS ownership and competing services first. Do not restart networking remotely without a physical recovery path. Switching supplicants may affect stored credentials; test existing networks and back up settings before switching.

Connectivity checking needs an administrator-selected HTTP endpoint, expected response and interval, installed as NetworkManager configuration. Use the distribution's existing valid probe when available. Do not hard-code a third-party tracking URL or assume connectivity checking is enabled by default. Endpoint configuration belongs to root provisioning, not the child's mutable UI.

### libnm adapter

`WifiBackend` exposes typed, immutable snapshots and cancellable operations:

- list compatible Wi-Fi devices and radio/hardware-rfkill status;
- request a scan (rate-limited), receive access point changes;
- activate a saved connection or create a parent-confirmed user-restricted connection;
- provide credentials using a registered `NM.SecretAgentOld` implementation when necessary;
- deactivate and forget only connections this session is authorized to manage;
- watch active connection/device state and reasons;
- expose NM connectivity (`unknown/none/limited/portal/full`) and run an explicit async recheck.

Use NM callbacks and `Gio.Cancellable`; no synchronous D-Bus waits on GTK. Every completion carries a request generation so leaving the screen or choosing a different network makes old callbacks harmless. NM restarts trigger resubscription and state refresh, not a launcher crash.

### Network display and credentials

- States: unavailable, radio off, hardware blocked, idle, scanning, connecting, connected/checking, portal required, limited, online, failed.
- Deduplicate access points by SSID **and compatible security family**. SSIDs are bytes; display undecodable names safely. Do not combine a rogue open AP with a saved WPA network merely because its name matches.
- Show signal strength, security, saved/active state and progress as text, not just icons.
- Support open networks (explicit warning), WPA2 personal and WPA3 personal when the installed backend supports them. Hidden personal networks use a dedicated form.
- Detect enterprise/802.1X and unsupported security and show an administrator message; implementing enterprise certificate policy is out of scope.
- Mask passwords, offer a show toggle, prevent invalid submissions, and clear UI buffers on cancel/finish. Never place secrets in argv, logs, JSON or the review database. If Remember is chosen, NetworkManager/iwd may persist credentials in their protected system stores: explain this boundary. Python cannot promise cryptographic erasure of every in-memory string.
- Store new NM profiles with permissions restricted to `leo`, subject to authorization tests. Do not casually edit/delete system-wide profiles created by the administrator.
- Connection cancel cancels UI operations and, if this request owns a new pending activation, deactivates that specific attempt; it does not disconnect an unrelated existing/just-switched connection.
- Handle wrong-password prompts, missing device, rfkill, scan throttling, DHCP/DNS failure, NM restart and service absence with actionable messages. A failed new connection should offer reconnecting to the previous saved network when possible, not silently strand the tablet.

### Authorization

Inspect `NM.Client` permission results before offering operations. Use current upstream polkit action names and verify installed policy; candidate required actions are:

- `org.freedesktop.NetworkManager.wifi.scan`
- `org.freedesktop.NetworkManager.network-control`
- `org.freedesktop.NetworkManager.enable-disable-wifi`
- `org.freedesktop.NetworkManager.settings.modify.own`

Grant only missing permissions to **user leo in an active local session**, scoped to these actions. Do not grant `settings.modify.system`, arbitrary system services, or a wildcard `org.freedesktop.NetworkManager.*`. If saved-connection management cannot work under restricted-profile permissions on the target version, escalate the design review; do not broaden policy just to pass a demo. Keep connection permissions as well as polkit policy in the test plan. No authentication agent is assumed to be installed in Cage.

### Portal lifecycle

1. After association/IP success, read NM connectivity and trigger a bounded async recheck.
2. `FULL`: show Online. `PORTAL`: show **Sign in to network**. `LIMITED/UNKNOWN`: show the actual state and offer manual **Open network login**; do not equate unknown with no portal.
3. Parent explicitly opens an embedded WebKitGTK view at the configured HTTP probe/login entrypoint so the network can redirect it. Do not derive a portal URL by scraping a guessed page or bypass HTTPS certificate errors.
4. Use a fresh ephemeral WebKit context/network session for the current Wi-Fi connection. Permit HTTP/HTTPS redirects needed for login. Display the current host with a warning that this is the network's page, not the tablet.
5. Visible controls: Back, Reload, keyboard toggle, **Check connection**, **Done**, **Cancel**. Navigation popups must remain within this isolated context; block downloads, filesystem/custom schemes, new external applications and unsolicited privileged permissions.
6. While open, recheck connectivity at a modest rate (e.g. 5 seconds, one outstanding request). Do not repeatedly POST/reload the login form. When full connectivity is detected, show success and Done; do not destroy the form automatically while the parent is typing.
7. Done/Cancel/return gesture closes the portal and returns to Wifi; Done does not falsely declare Online without NM confirmation. Destroy the portal context and credentials on network change or leaving the workflow.
8. If checks are disabled or the probe itself is blocked, show “Connectivity cannot be verified”; allow the parent to retry/open login manually. Never treat a failed probe as definitive internet failure.
9. TLS errors remain blocked with an explanation. OAuth/popups, SMS flows, browser-dependent portals and unusual 802.1X flows are compatibility risks, tested where required, not guaranteed.

### Touch keyboard acceptance gate

A portable global on-screen keyboard is not assumed to work under Cage. Implement one GTK component for launcher name/rating/Wi-Fi fields. For WebKit portal fields, prototype WebKit's focused-frame editing commands (`can_execute_editing_command`, `execute_editing_command_with_argument`) with a non-focus-stealing keyboard container. Confirm insert/delete/cursor/submit behavior with password inputs, UTF-8, HTTPS redirects and cross-origin iframe fields.

If the prototype cannot provide reliable touch-only login without weakening WebKit security, **block portal release and revise the keyboard/compositor decision**. Do not ship a physical-keyboard-only fallback as meeting the tablet requirement. A compositor migration is a separate ADR and scope change, not a junior developer workaround.

## 11. Resilience, privacy, and limits

- Startup: migrate/restore safely, import idempotently, recover unfinished review sessions, render nine slots even offline.
- Disk full/read-only/corrupt DB: show a parent diagnostic, do not reset to an empty database or overwrite prior data. A last valid home snapshot may be used read-only if implemented and explicitly labeled.
- Browser crash or timeout: return to the correct screen and retain trial evidence/drafts. A launcher crash loses unsaved draft text, but not committed reviews or slot assignments; offer recovered trial review on restart.
- In-memory drafts are never committed by an accidental gesture. Ask before leaving the editor; don't silently approve a game.
- Suspend/resume: clear gesture buffer and refresh devices/network state. Playback deadlines use Linux `CLOCK_BOOTTIME`, which includes suspended time and is unaffected by wall-clock corrections; both child limits and the 30-minute parent trial limit include sleep. Recheck immediately on wake and terminate expired sessions. Persist UTC times for history only; boot-clock deadlines cannot be resumed across reboot, and historical sessions are recovered as abandoned rather than relaunched. Parent trial deadline may be reset only by explicit retry.
- Avoid logging credentials, input text, full portal URLs with tokens, query strings, general keyboard events or browser history. Log event kind, stable IDs, correlation/session ID and sanitized errors.
- Keep library error text out of GTK markup. Save local data only; no account, cloud sync, telemetry or upload endpoint in this scope.
- Multi-user editing, DRM video playback, camera/microphone permissions, enterprise Wi-Fi, remote management and guaranteed child web filtering are explicitly out of scope.

## 12. Tests and release gates

### Automated

- Gesture unit/property tests: exact sequences, time boundaries, wrong-prefix suffixes, repeat/release noise, cooldown, context reset, duplicate device source and simulated suspend.
- Domain/storage: four status badges, idempotent imports, ignored videos/hubs, tombstones, rename/rating validation, 0 versus null, slot uniqueness/capacity/replacement/move, stale revision, transaction rollback and migration recovery.
- Queue: deterministic next, filtering, deletion, rename/sort changes, queue end, failed next launch.
- Process fakes and controlled real subprocesses: spawn failure, natural exit, TERM/KILL escalation, duplicate callbacks, stale timers, repeated taps, profile lock errors, correct return route, leftover child processes.
- libnm adapter with dbusmock/custom fixtures: scan, SSID/security grouping, secret requests/cancel, errors, NM restart, authorization denied, connecting request supersession, portal/full/unknown/limited transitions.
- Controlled local portal fixture: HTTP redirect, login form, password, iframe, popup, self-signed TLS rejection, fake online transition. No automated test connects to real personal Wi-Fi credentials.
- GTK smoke: nine grey tiles/three labels, keyboard focus, filter restoration, fixed action bar, confirmations, visible error banners.

### Surface Go manual acceptance (mandatory)

1. Boot offline: child and parent grids render nine tiles with correct geometry.
2. Use physical buttons at normal and fast speeds while GTK, Firefox and portal have focus. Old Down/Up shortcut does not trigger.
3. Review one working landscape game, one portrait game, one account-gated/blocked game and one game that fails to start.
4. Return with Down/Down/Up; rename with touch keyboard, rate 0 and 100, keep/select/delete; verify persistence after reboot.
5. Select into an occupied legacy slot, replace another selected game, move an assignment, unselect and delete; no hidden tenth game or stale tile.
6. “Ok and see next” maintains queue and stops at the end; unsaved changes prompt.
7. Test time limit, browser crash, input-device removal, suspend/resume and network loss without orphaned windows/processes.
8. Connect to open, WPA2 and supported WPA3 networks, wrong password, hidden network, remember/forget; verify permissions as leo.
9. Complete captive portal using **touch only**; verify cross-origin/password fields, connectivity recheck and failure/Cancel paths.
10. Confirm portal state/cookies do not enter child Firefox; no secrets in logs/argv/SQLite exports.
11. Exit returns to child home, not a console. Administrator SSH/recovery and networking rollback still work.

Release gates: platform audit passed; portal keyboard prototype passed; all transaction/gesture tests passed; hardware matrix recorded; permissions reviewed; installer and rollback rehearsed. No live root or network changes during architecture work.

## 12b. Web-based kiosk UI (owner decisions, 2026-10-24 and 2026-10-25)

The owner approved re-platforming the **parent UI** onto a local web stack
(2026-10-24), superseding the historical no-web-frontend constraint. On
2026-10-25 the owner extended this to **all UI**: every screen — child home,
Videos, parent mode — is an HTML page on the loopback server shown in one
WebKitGTK view. The measured trigger: the Firefox parent browser cost
~921 MB PSS across 12 processes for one server-rendered page; the WebKitGTK
replacement measures ~225 MB across 3 (`tools/memprobe.py` on the tablet).

- The launcher process hosts one fullscreen `WebKit2.WebView` (ephemeral
  context, `ui/window.py`) and a loopback HTTP server thread
  (`adapters/ui_server.py`) rendering every page from the existing services.
- The server binds `127.0.0.1` only. Per the owner (2026-10-24): child safety
  hardening is deferred; the Up/Down/Down gesture is the only gate for now, so no
  token is required. The loopback bind remains so LAN devices cannot reach it.
- Routes map to server pages (`URL_FOR` in `application.py`): `/` child home,
  `/videos`, `/parent`, `/review`, `/wifi`. The parent gesture and return
  gestures navigate the view; launched apps hide it, exactly like the GTK
  window they replace.
- Launch behavior (voices, `alt` fallbacks, `.app-pid`, deadline TERM→KILL,
  status line, five-tap corner exit) moved unchanged into
  `services/tile_launch.py`; the server thread marshals web actions to the GTK
  main thread via `GLib.idle_add`. Video playback still spawns through the
  allowlisted `videos.py` argv[0] (`videos.py <url>` runs mpv), so leopowerd
  and backwatch contracts are unchanged.
- The rainbow and battery gauge are re-implemented in the page's JS/HTML with
  the same parameters (`RAINBOW_JS`, `CHILD_CSS`); battery state comes from
  the polled `/child-state` endpoint.
- The server thread owns its own SQLite connection (`open_database` is per-thread by
  contract); the HTTP server is deliberately single-threaded so one connection serves
  all requests.
- Game trials and the captive portal keep using Firefox (compatibility and
  sandbox); the review/rename/rating/Wi-Fi parent tasks remain web endpoints.

## 13. Implementation sequencing and estimates

See `backlog.md` and `tasks.json` for the original 68-task backlog with Fibonacci sizes. The authoritative implementation graph is now [specs.md](../../specs.md), refined into 90 atomic tasks with per-type model assignments; [implementation-status.md](implementation-status.md) records completion. The SQLite startup/migration/fault work was split into parent-8, parent-87 and parent-88; catalog schema/metadata/record persistence is split into parent-9, parent-89 and parent-90. The latest input-format decision permits rearranging or removing `web-games.json` after verified SQLite migration and fresh-install bootstrap coverage. Original Fibonacci sizes describe relative complexity, not days.

Phase order:

1. Platform/UX decisions and dependency spikes (especially touch portal).
2. Testable domain/storage plus launcher/module extraction.
3. Gesture and owned-process lifecycle.
4. Parent menu, catalog list, review editor, home assignments.
5. libnm Wi-Fi and portal workflows.
6. Provisioning, full regression, tablet acceptance and rollout.

Networking work can proceed alongside review UI once adapter contracts exist. Do not let a large network integration task block independent catalog/domain tests. Tasks with an unresolved hardware dependency are blocked, not “done with assumptions.”

## 14. References

- Current repository files listed in section 2.
- NetworkManager configuration: https://networkmanager.dev/docs/api/latest/NetworkManager.conf.html
- libnm client: https://networkmanager.dev/docs/libnm/latest/NMClient.html
- libnm secret agent: https://networkmanager.dev/docs/libnm/latest/NMSecretAgentOld.html
- NetworkManager policy source: https://github.com/NetworkManager/NetworkManager/blob/main/data/org.freedesktop.NetworkManager.policy.in
- Arch package/dependency reference: https://archlinux.org/packages/extra/x86_64/networkmanager/
- iwd configuration: https://man.archlinux.org/man/iwd.config.5.en
- evdev: https://python-evdev.readthedocs.io/en/latest/tutorial.html
- pyudev: https://pyudev.readthedocs.io/
- Cage: https://github.com/cage-kiosk/cage and https://github.com/cage-kiosk/cage/blob/master/cage.c
- wvkbd protocol requirements: https://github.com/jjsullivan5196/wvkbd
- WebKitGTK 4.1 ephemeral context: https://webkitgtk.org/reference/webkit2gtk/stable/ctor.WebContext.new_ephemeral.html
- WebKitGTK editing API: https://webkitgtk.org/reference/webkit2gtk/stable/method.WebView.execute_editing_command_with_argument.html
- jsonschema: https://python-jsonschema.readthedocs.io/
- Hypothesis: https://hypothesis.readthedocs.io/
- python-dbusmock: https://github.com/martinpitt/python-dbusmock

Upstream pages/source establish API availability, not target-device compatibility. Record installed package versions and actual behavior during the platform audit; do not pin an untested version based only on this document.
