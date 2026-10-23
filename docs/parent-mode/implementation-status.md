# Parent-mode implementation status

The feature is **partially implemented, not integrated into the launcher**. Existing child tiles, shortcuts, process launching and system configuration are unchanged. The original discovery file is unchanged.

## Completed execution-plan tasks

| Task | Implemented scope | Files |
|---|---|---|
| parent-1 | Editable Python package, development dependencies, pytest/Ruff/mypy configuration, temporary storage/D-Bus isolation, network guards, inert clock/process fixtures and explicit hardware/display opt-ins | `leo-kiosk/pyproject.toml`, `leo-kiosk/tests/conftest.py`, `test_harness.py`, `.gitignore` |
| parent-5 | Immutable catalog values; media/orientation/dimension-evidence enums; conservative HTTP(S) normalization; stable UUIDv5 identities; launch-URL overrides do not change source identity | `leo-kiosk/leo_kiosk/domain/catalog.py`, `test_catalog_model.py` |
| parent-6 | Validated review drafts, home-slot DTOs, review enums/service protocols, launch roles/outcomes/ownership contexts and typed errors | `domain/reviews.py`, `domain/sessions.py`, `domain/errors.py`, `test_review_model.py` |
| parent-21 | Both three-tap patterns, injected monotonic clock, configurable gap/window/cooldown, consumed matches, longest valid suffix, reset reasons and noise handling | `domain/gestures.py`, `test_gestures.py` |

The domain files above are under `leo-kiosk/leo_kiosk/`; test files are under `leo-kiosk/tests/unit/`. Protocols define interfaces only: storage, process control and GTK implementations are not yet provided.

## Verification

Executed in a project-local virtual environment using Python 3.14.8:

- Unit/property tests: **93 passed**.
- Ruff lint and formatting: pass for the new code; lint also covers the unchanged legacy scripts.
- Strict mypy: pass for the domain package.
- Tests cover URL authority/control/userinfo validation and identity-sensitive query/fragment preservation; unknown versus popup/design size evidence; null/zero/rating/name boundaries; home occupancy; launch role/token/UTC context; exact/noisy/expired/reset/cooldown gestures and an exhaustive short-stream reference model.

Reproduce with the commands in [development.md](development.md). No target-device or GTK integration acceptance has been performed.

## Not yet complete

- parent-2 platform audit, parent-3 touch portal spike and parent-4 libnm/iwd permission spike require measured target-device evidence. No assumptions have been recorded as passes.
- Parent GTK screens, catalog normalization/import, SQLite persistence, evdev integration, owned Firefox sessions, Wi-Fi controls and portal implementation remain pending.
- New gestures are only a tested domain recognizer. The production watcher still uses the old Down/Up shortcut until the planned integration/cutover tasks are completed.
- No installer, root configuration, Wi-Fi service, polkit policy, input permissions or physical device setting was changed.

## Next independent slices

- parent-8: safe SQLite bootstrap/migrations, now unblocked by the domain contracts.
- parent-7: extract the GTK shell while retaining current behavior.
- parent-11: audit discovery records/provenance before generating a playable catalog.
- parent-2: obtain the actual Surface Go audit before hardware/network integration.

Do not release parent mode until the remaining architecture gates and Surface Go acceptance tasks pass. Full plan: [specs.md](../../specs.md).
