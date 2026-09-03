# Abletools

Abletools is the deterministic asset engine and catalog behind the **Abletools GPT**. It creates, validates, versions, and stores original Ableton-ready building blocks in two modes:

- `DRUIID`: seed-recallable, scale-aware systems with controlled mutation.
- `HAZY`: original hazy-analog material using broad aesthetic traits without copying any artist's work.

## Capability boundary

| Asset | Status |
|---|---|
| Standard MIDI files | Generated and strictly validated |
| DRUIID MIDI Essentials | Enabled: chord, bass, motif, and drum A/B/C clips |
| HAZY MIDI Essentials | Gated for its separate profile-backed milestone |
| 48 kHz / 24-bit PCM WAV | Generated and validated |
| ZIP packs + manifests | Deterministically generated and validated |
| Serum 2 presets | Gated pending licensed fixture/export harness |
| Ableton racks/grooves/devices | Gated pending native fixture/export harness |

Never disguise text or JSON as a native preset. The file extension is not a trench coat.

## Quick start

Requires Python 3.11+ and no runtime dependencies.

```bash
python -m pip install -e .
abletools demo --output build/demo --seed 1842
abletools validate build/demo
abletools druiid-midi --output build/druiid-midi --seed 1842 --root A --scale minor
abletools validate build/druiid-midi
abletools validate build/druiid-midi.zip
python -m unittest discover -s tests
```

The demo creates a deterministic chord MIDI file, a synthesized kick WAV, `manifest.json`, and a ZIP pack.
The DRUIID command creates twelve MIDI clips: A/B/C forms for chords, bass, motif, and drums.
Every pack includes a README, complete metadata and validation records, and a deterministic validated ZIP.

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

R2 adds a standards-compliant DRUIID MIDI Essentials vertical slice, strict manifest and MIDI checks,
an explicit runtime capability registry, and safe deterministic ZIP validation. DRUIID remains a
provisional musical-behavior profile rather than a claimed sonic genre. HAZY generation, publication,
and all native Serum 2 and Ableton formats remain gated for their separate milestones.
