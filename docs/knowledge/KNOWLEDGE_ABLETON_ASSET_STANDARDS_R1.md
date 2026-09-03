# Ableton asset standards R1

## General deliverable rule

Return genuine, validated files. A descriptive recipe is not a preset, rack, device, groove, or sample. Use a fallback document only when native generation is unavailable and the user accepts that form.

## MIDI clips

- Use Standard MIDI Format 0 or 1 that imports correctly into Ableton Live.
- Include a tempo event and 4/4 meter unless the request specifies otherwise.
- Use a musically correct clip length with no trailing accidental bar.
- End every note cleanly. Prevent stuck notes, zero-length notes, and invalid event ordering.
- Keep pitched instruments in practical ranges and drums on declared MIDI notes.
- Use note velocity intentionally.
- Put tempo, key/scale, bars, seed, and role in the manifest.
- For chord material, include degree sequence and chord symbols in metadata.
- If a groove is delivered as MIDI, include a simple reference pattern so timing and velocity can be extracted or copied in Live.

Suggested default General MIDI drum mapping:

| Role | Note |
|---|---:|
| Kick | 36 |
| Snare | 38 |
| Clap | 39 |
| Closed hat | 42 |
| Pedal hat | 44 |
| Open hat | 46 |
| Low percussion | 45 or 47 |
| High percussion | 50 or 54 |

Declare any deviation.

## WAV audio

- Default to 48 kHz, 24-bit PCM WAV.
- Use mono for centered low-frequency one-shots unless stereo information is meaningful.
- Use stereo for beds, spatial FX, and transitions when appropriate.
- Remove DC offset and accidental leading/trailing silence.
- Add microscopic fades to prevent clicks without blunting deliberate transients.
- Leave peak headroom; do not normalize every sound into a brick.
- One-shots should begin promptly and preserve deliberate decay.
- Loops must be sample-accurate for the stated bar count and tempo.
- Check loop boundaries for clicks and discontinuities.
- Do not embed uncleared recordings or copyrighted samples.

## Drum-pack expectations

Each family should contain meaningfully different sounds, not trivial gain or pitch duplicates. Useful variation dimensions include body, transient, brightness, decay, noise character, pitch, room amount, and saturation. Keep sub-heavy kicks phase-stable and keep unnecessary stereo energy out of the lowest frequencies.

## Serum 2 presets

Native Serum 2 presets may be returned only through a tested exporter compatible with the user's Serum 2 version.

A valid preset design should specify:

- oscillator/noise sources and tuning
- wavetable position or source selection
- filter routing and cutoff/resonance/drive
- amp and modulation envelopes
- LFO shapes, rates, modes, and destinations
- modulation matrix depths
- effects and order
- macro names, ranges, and musical purpose
- voice/unison behavior
- output/gain safety

Recommended macros are four to eight performance controls. Avoid mappings that cause extreme level jumps or unusable edge states. A text or JSON build sheet must be labeled as a build sheet, never as a native preset.

## Ableton audio and MIDI racks

- Prefer stock Live devices unless the user requests third-party dependencies.
- Record the required Ableton Live version and device dependencies.
- Devices process from left to right; design and document gain staging accordingly.
- Use a concise set of musically useful macros. Live supports up to 16 Rack Macro Controls, but fewer are often better.
- Define macro minimum/maximum ranges, polarity, and any inverted mappings.
- When useful, include a small set of Macro Variations representing safe starting states.
- Validate that the rack opens, dependencies resolve, mappings move the intended parameters, and bypass does not create a dangerous level jump.
- Without a tested native exporter, deliver only a clearly labeled rack map if the user accepts it.

## Max for Live and code tools

- A functioning Max for Live device normally includes an `.amxd` plus any required JavaScript, audio, image, data, or abstraction sidecars.
- Keep relative references intact and package dependencies together.
- Moving or renaming sidecars can break a device; instruct the user to keep the folder intact in the Ableton User Library or another indexed Place.
- Source code alone is not a tested `.amxd` device.
- Include a version, short README, input/output assumptions, and a smoke-test procedure.

## Pack structure

Use this structure when returning multiple assets:

```text
PACK_NAME/
  README.md
  manifest.json
  MIDI/
  WAV/
  PRESETS/
  RACKS/
  TOOLS/
```

Create only the folders actually used.

## Filenames

Use filesystem-safe names:

```text
STYLE_ROLE_DESCRIPTOR_[BPM]_[KEY]_S####_V##.ext
```

Examples:

```text
DRUIID_CHORDS_OPEN_120_Amin_S1842_V01.mid
HAZY_KICK_SOFTBODY_S0714_V03.wav
HAZY_ATMO_FADE_088_Cmaj_S6021_V01.wav
```

Use `DRUIID` or `HAZY`, not an artist name.

## Manifest minimum

```json
{
  "pack_name": "example",
  "version": "1.0.0",
  "style": "DRUIID",
  "asset_type": "midi_chords",
  "seed": 1842,
  "tempo_bpm": 120,
  "meter": "4/4",
  "key": "A minor",
  "files": [],
  "format": {},
  "generation_notes": [],
  "validation": [],
  "dependencies": []
}
```

Use `null` or omit fields that genuinely do not apply; do not invent validation results.
