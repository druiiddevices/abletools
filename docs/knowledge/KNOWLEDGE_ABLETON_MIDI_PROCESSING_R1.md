# Ableton MIDI processing R1

## Purpose and authority boundary

This file is the canonical R1 reference for Abletools MIDI Effect Rack blueprints. It covers verified stock-device concepts in Ableton Live 12 and the safe processing contract for `MIDI_PATTERN_MUTATOR`. It does not define native Ableton serialization keys and does not authorize `.adg`, `.adv`, `.agr`, or `.amxd` export.

Use stable Abletools registry identifiers in blueprint JSON. A registry identifier is a build-specification vocabulary mapped to a control documented in the Live 12 manual; it is not a claim about Live's internal file representation.

## Verified stock MIDI stages

| Registry device | Live device | R1 use |
|---|---|---|
| `scale` | Scale | Base/scale selection, Current Scale awareness, transpose, fold, and bounded note range |
| `chord` | Chord | Six bounded pitch shifts, per-shift velocity/chance, strum, tension, crescendo, and Current Scale awareness |
| `arpeggiator` | Arpeggiator | Style, synchronized rate expressed as musical divisions, gate, distance, steps, retrigger, and Current Scale awareness |
| `random` | Random | Bounded chance, choices, interval, mode, sign, and Current Scale awareness |
| `note_length` | Note Length | Note-on/off trigger source, gate, musical length, release velocity, and release decay |
| `velocity` | Velocity | Input window, output bounds, operation/mode, and bounded velocity deviation |

These controls are documented in the Ableton Live 12 MIDI Effects reference. If a device or parameter is absent from the closed runtime registry, validation must reject it. Extend the registry only after verifying the public Live manual and adding focused tests.

## Routing contract

A MIDI Effect Rack blueprint contains MIDI-effect stages only. It must not include an instrument, audio effect, audio dry/wet control, audio output trim, limiter, gain staging claim, latency compensation claim, or audio-tail claim.

Device order must be musically legible and preserve note safety. Typical bounded flows include:

```text
Scale -> Chord -> Arpeggiator -> Random -> Note Length -> Velocity
Random -> Scale -> Chord -> Arpeggiator -> Note Length -> Velocity
```

Putting Scale after Random is useful when the output must be returned to the selected scale. Alternative orders require an explicit musical reason and the same outgoing-note guarantees.

## Neutral and note-safety behavior

- Every macro declares a true neutral value. Do not force a hidden nonzero minimum at macro zero.
- Random chance and velocity deviation default to zero when neutral.
- Transposition defaults to zero; optional chord tones can be silent at neutral.
- Generated or transformed notes must remain within MIDI note 0–127 and velocity 1–127.
- Every emitted note-on must have one bounded note-off. Never create hanging notes, unbounded feedback, or self-running random behavior.
- Note length and arpeggiator gate ranges must remain finite and musically usable.
- Range limiting must be explicit. Do not rely on an unspecified receiving instrument to discard unsafe notes.
- Random output must be bounded by declared chance, choice, interval, scale, and note-range controls.
- A deterministic blueprint may describe controllable randomness, but its topology, defaults, mappings, and variations must be byte-identical for the same inputs and seed.

## Macro and variation contract

`MIDI_PATTERN_MUTATOR` exposes exactly 12 complete macros. At least four coordinate more than one real registry target. Named variations are `INIT`, `SUBTLE`, `ACTIVE`, and `EXTREME_SAFE`; each covers every macro. `INIT` uses every declared neutral value.

Macro ranges must reflect discrete device semantics where appropriate. Integer controls such as arpeggiator rate divisions, Random choices, or Scale range are declared with integer endpoints. Each target includes its full device path, parameter ID, bounds, neutral point, direction, and musical purpose.

## Validation boundary

Blueprint validation can prove JSON-schema shape, closed-registry membership, MIDI-only topology, path resolution, parameter domains, macro completeness, deterministic bytes, manifest integrity, and ZIP integrity. It cannot prove a native rack opens, recalls, or sounds useful in Ableton Live.

After manual construction in Live, native approval still requires note-on/off tests, range and velocity tests, held-note and retrigger tests, automation boundary tests, deterministic recall checks, and save/reopen verification. Until fixture-based round-trip tests exist, native Ableton export remains gated.

## Primary reference

- [Ableton Live 12: MIDI Effects](https://www.ableton.com/en/manual/live-midi-effect-reference/)
