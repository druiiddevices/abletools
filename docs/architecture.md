# Architecture and capability gates

## Flow

```text
request -> normalized parameters -> derived seed -> generator -> validator
        -> manifest + checksums -> packager -> catalog/publisher
```

Each stage has one job. Generation cannot mark its own output as validated; validators inspect the written bytes.

## R1

R1 is intentionally narrow:

- standard-library deterministic seed derivation
- type-0 Standard MIDI writer and parser/validator
- 48 kHz, 24-bit PCM WAV synthesizer and validator
- manifest contract with relative paths and SHA-256 checksums
- ZIP packaging
- CLI and CI smoke tests

This foundation proves that Abletools can make real assets rather than persuasive filenames.

## Asset catalog

Released packs belong under:

```text
assets/<STYLE>/<CATEGORY>/<PACK_NAME>/<VERSION>/
```

Where:

- `<STYLE>` is `DRUIID` or `HAZY`.
- `<CATEGORY>` is `MIDI`, `DRUMS`, `SAMPLES`, `SERUM2`, `RACKS`, `GROOVES`, or `TOOLS`.
- Every version is immutable and contains `manifest.json`.
- Large/binary assets use Git LFS.

## Native exporter gate

A native format may move from `gated` to `enabled` only when all are true:

1. A user-owned file exported by the target application is stored as a private test fixture or cryptographic reference.
2. The minimum supported application/plugin version is recorded.
3. The generated file opens in the target application without repair dialogs.
4. Parameters, macros, dependencies, and audio/MIDI behavior match the manifest.
5. Round-trip or golden-fixture tests run repeatedly on clean outputs.
6. Failure returns an explicit error and never publishes the asset.

This applies independently to Serum 2 presets, Ableton `.adg`/`.adv` racks, `.agr` grooves, and `.amxd` devices.

## GPT Action phase

The upload service should expose narrowly scoped authenticated operations:

- `create_asset_job`
- `get_asset_job`
- `validate_asset`
- `publish_asset_pack`
- `list_asset_packs`
- `download_asset_pack`

The service—not the GPT—owns repository credentials, rate limits, validation, idempotency, and publication. Generated work first enters a staging branch or release job; it does not receive arbitrary repository write access.
