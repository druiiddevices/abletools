# Abletools

Abletools is the deterministic asset engine and catalog behind the **Abletools GPT**. It creates, validates, versions, and stores original Ableton-ready building blocks in two modes:

- `DRUIID`: seed-recallable, scale-aware systems with controlled mutation.
- `HAZY`: original hazy-analog material using broad aesthetic traits without copying any artist's work.

## Capability boundary

| Asset | Status |
|---|---|
| Standard MIDI files | Generated and strictly validated |
| DRUIID MIDI Essentials | Enabled: chord, bass, motif, and drum A/B/C clips |
| HAZY MIDI Essentials | Enabled: chord, bass, motif, arpeggio, and GM drum A/B/C clips |
| DRUIID Drum One-Shot Essentials | Enabled: 40 synthesized source WAVs plus source-only preview |
| HAZY Drum One-Shot Essentials | Enabled: 40 synthesized source WAVs plus source-only preview |
| 48 kHz / 24-bit PCM WAV | Generated with strict signal and container validation |
| ZIP packs + manifests | Deterministically generated and validated |
| Ableton rack blueprint JSON | Enabled: deterministic, strictly validated build specifications |
| Serum 2 presets | Gated pending licensed fixture/export harness |
| Native Ableton racks/grooves/devices | Gated pending native fixture/export harness |

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
abletools hazy-midi --output build/hazy-midi --seed 1842 --root D --mode dorian
abletools validate build/hazy-midi
abletools validate build/hazy-midi.zip
abletools rack-blueprints --output build/racks-druiid --style DRUIID --seed 1842
abletools validate build/racks-druiid
abletools validate build/racks-druiid.zip
abletools rack-blueprints --output build/racks-hazy --style HAZY --seed 1842
abletools validate build/racks-hazy
abletools validate build/racks-hazy.zip
abletools drum-essentials --output build/drums-druiid --style DRUIID --seed 1842
abletools validate build/drums-druiid
abletools validate build/drums-druiid.zip
abletools drum-essentials --output build/drums-hazy --style HAZY --seed 1842
abletools validate build/drums-hazy
abletools validate build/drums-hazy.zip
python -m unittest discover -s tests
```

The demo creates a deterministic chord MIDI file, a synthesized kick WAV, `manifest.json`, and a ZIP pack.
The DRUIID command creates twelve MIDI clips: A/B/C forms for chords, bass, motif, and drums.
The HAZY command creates fifteen original MIDI clips: A/B/C forms for chords, bass, motif,
rhythmic harmony/arpeggios, and General MIDI drums. It supports major, minor, Dorian,
Mixolydian, Lydian, and Aeolian modes plus explicit harmonic, color, tension, pedal,
common-tone, groove, and role-mutation controls. Run `abletools hazy-midi --help` for the full surface.
Every pack includes a README, complete metadata and validation records, and a deterministic validated ZIP.
The rack commands each create five JSON build specifications under `RACKS/BLUEPRINTS`: two Audio
Effect Racks, two Operator Instrument Racks, and one MIDI Effect Rack. These are validated construction
documents, not native Ableton rack files. Native export remains gated.
Each Drum Essentials command synthesizes 8 kicks, 8 snares, 6 closed hats, 4 open hats,
6 shakers, and 8 percussion one-shots. Every source is mono 48 kHz / 24-bit PCM and has
family-bounded duration, conservative headroom, DC, silence, fade, waveform-shape, checksum,
and metadata validation. The additional preview is reconstructible from declared included sources.

## Repository map

```text
assets/       Versioned released assets and catalog guidance
docs/         Architecture and native-export gates
examples/     Small runnable examples
schemas/      Asset manifest and rack-blueprint JSON Schemas
src/          Generator, validator, and CLI code
tests/        Determinism and file-integrity tests
```

See [docs/architecture.md](docs/architecture.md) before adding an exporter or upload API.

## Current phase

The current phase includes separate standards-compliant DRUIID and HAZY MIDI Essentials implementations, strict
manifest and MIDI checks, an explicit runtime capability registry, and safe deterministic ZIP validation.
Milestone 3A adds a closed Live 12 stock-device/parameter registry and deterministic DRUIID/HAZY rack
blueprint packs with strict topology, macro, variation, safety, manifest, checksum, and ZIP checks.
Milestone 4A adds independent DRUIID and HAZY original drum-synthesis profiles, isolated family/voice
random streams, exact 40-source catalogs, strict canonical WAV inspection, gain-normalized shape
deduplication, reconstructible previews, and deterministic ZIP validation.
DRUIID remains a provisional musical-behavior profile rather than a claimed sonic genre. HAZY is an
original profile built from broad modal, textural, repetition, and timing principles; it is not an artist
recreation system. Publication and all native Serum 2, Ableton, and Max for Live formats remain gated.
Generated smoke assets remain under `build/`; no listening or release approval is implied.
