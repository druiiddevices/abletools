# Abletools

Abletools is the deterministic asset engine and catalog behind the **Abletools GPT**. It creates, validates, versions, and stores original Ableton-ready building blocks in two modes:

- `DRUIID`: seed-recallable, scale-aware systems with controlled mutation.
- `HAZY`: original hazy-analog material using broad aesthetic traits without copying any artist's work.

## R1 capability boundary

| Asset | R1 status |
|---|---|
| Standard MIDI files | Generated and validated |
| 48 kHz / 24-bit PCM WAV | Generated and validated |
| ZIP packs + manifests | Generated and validated |
| Serum 2 presets | Gated pending licensed fixture/export harness |
| Ableton racks/grooves/devices | Gated pending native fixture/export harness |

Never disguise text or JSON as a native preset. The file extension is not a trench coat.

## Quick start

Requires Python 3.11+ and no runtime dependencies.

```bash
python -m pip install -e .
abletools demo --output build/demo --seed 1842
abletools validate build/demo
python -m unittest discover -s tests
```

The demo creates a deterministic chord MIDI file, a synthesized kick WAV, `manifest.json`, and a ZIP pack.

## Repository map

```text
assets/       Versioned released assets and catalog guidance
docs/         Architecture and native-export gates
examples/     Small runnable examples
schemas/      Asset manifest JSON Schema
src/          Generator, validator, and CLI code
tests/        Determinism and file-integrity tests
```

See [docs/architecture.md](docs/architecture.md) before adding an exporter or upload API.

## Current phase

R1 establishes trustworthy MIDI/WAV generation and a manifest contract. The next phase adds an authenticated GPT Action service and repository publication workflow. Native Serum 2 and Ableton formats remain disabled until real user-exported fixtures pass round-trip tests.
