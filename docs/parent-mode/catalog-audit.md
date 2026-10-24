# Catalog audit

Source: [web-games.json](../../web-games.json), a temporary discovery input with **no fixed format or permanent-file requirement** (owner decision). SQLite is authoritative. This audit accounts for the input as it currently exists so later import/bootstrap work can be verified against it.

## Current counts (input as found, not a target)

- 14 provider groups, 109 entries: **93 labeled game, 16 video, 0 other**.
- Two providers have zero entries (Hugo l'escargot, Boukili); they remain in the file as source context.
- These counts describe the input. They are **not** the expected eligible/playable game count, and the application must not hard-code either number.

## Format flexibility

The original six-key export contract (name/url/is_landscape/width/height/type with 0/0 for unknown size and false placeholders for unknown orientation) is **superseded**. A versioned `catalog/bootstrap.json` will feed fresh installs; its format follows domain DTOs and validation schema, not the discovery file. After verified import/restart parity, the JSON may be rearranged or deleted; references and fixtures must be updated then, not before.

## Provenance

- `catalog/provenance.json` records the source checksum (`1dcf4dfe…` for the current bytes), evidence legend, exclusions and a reconciliation entry per provider/source index. All 109 input records are accounted for: 107 eligible, 2 excluded. Playback evidence remains "discovered" until a parent trial runs.
- HTTP 200 during discovery is **not** proof a URL is a single game or that it plays. It was recorded as evidence only.

## Confirmed exclusions (ineligible for game slots)

| Provider | Source index | Entry | Reason |
|---|---|---|---|
| Starfall | 6 | Fun to Read section | Section page, not a single activity |
| Sesame Street | 5 | Games page entry | Hub listing entry; individual game ids remain |

Any later-discovered hub/section link must be added here with its source index rather than silently skipped.

## Dimension evidence caveats

| Provider | Scope | Evidence | Note |
|---|---|---|---|
| Gulli | all 43 items | popup | 800×600 / 600×800 are launcher window sizes from Gulli's own code, **not game canvas resolutions** |
| Lumni | sample | inferred | 708×600 was verified for one game only; the rest inferred |
| Starfall | all 7 items | design | 1024×768 verified for letter-a; letters assumed to share the design size |
| all others | — | unknown | No per-item measurements existed |

## Special cases

- **Sesame Street** uses query-based URLs (`games?id=...`). A query parameter can identify an individual game; do not treat query-based URLs as hubs purely because of their path.
- **Gulli** items are geo-blocked from this machine (CloudFront 403); URLs remain valid for a French network, and orientation metadata comes from Gulli's own launcher code.
- **Videos** (Mystery Science, Cosmic Kids, Okoo, TFO) stay out of the game queue; a video review viewer is out of scope this release.

## Verification

```sh
python3 -m json.tool web-games.json
python3 -m json.tool catalog/provenance.json
```

A checker (part of parent-12) will assert every provider/source index in the input appears exactly once in the provenance reconciliation and that counts match. Full plan: [../.. /specs.md](../../specs.md).
