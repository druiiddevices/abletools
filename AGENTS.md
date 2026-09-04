# Abletools agent rules

## Mission

Build original, useful Ableton Live assets and the infrastructure that validates and catalogs them.

## Non-negotiable rules

- Preserve deterministic output for identical inputs and seeds.
- Validate every generated binary before publishing it.
- Never fake `.SerumPreset`, `.adg`, `.adv`, `.agr`, `.amxd`, MIDI, WAV, or ZIP contents.
- Native Serum 2 and Ableton exporters stay disabled until fixture-based round-trip tests pass.
- Do not reproduce recognizable melodies, samples, presets, loops, or arrangements from an artist.
- Use `DRUIID` and `HAZY` as internal style identifiers. Do not put artist names in asset filenames.
- Keep generated binaries out of ordinary Git history unless they are approved release assets and covered by Git LFS.
- Every released pack needs a valid `manifest.json` and validation record.

## Required knowledge routing

Before designing, generating, reviewing, or approving an asset, read:

1. `docs/knowledge/KNOWLEDGE_ABLETON_ASSET_STANDARDS_R1.md`
2. The requested style profile:
   - `docs/knowledge/KNOWLEDGE_DRUIID_STYLE_R1.md` for `DRUIID`
   - `docs/knowledge/KNOWLEDGE_BOC_STYLE_R1.md` for `HAZY`
   - both style files only for an explicitly requested hybrid
3. For Audio Effect Racks, Instrument Racks, Operator instruments, or sound-design tools, also read
   `docs/knowledge/KNOWLEDGE_ABLETON_RACKS_R1.md`.
4. For MIDI Effect Racks or MIDI-processing blueprints, also read
   `docs/knowledge/KNOWLEDGE_ABLETON_MIDI_PROCESSING_R1.md`.

The knowledge files define asset/style intent. This `AGENTS.md` defines repository execution rules. Do not silently invent new Druiid traits or change a style profile from a single output; keep observations separate until the user approves them. Rack blueprints and native `.adg` export are separate capabilities: blueprint work may proceed before native export, but a blueprint must never be presented as a finished rack.

## Verification

Run before committing:

```bash
python -m unittest discover -s tests
python -m abletools.cli demo --output build/smoke --seed 1842
python -m abletools.cli validate build/smoke
python -m abletools.cli rack-blueprints --output build/racks-druiid --style DRUIID --seed 1842
python -m abletools.cli validate build/racks-druiid
python -m abletools.cli rack-blueprints --output build/racks-hazy --style HAZY --seed 1842
python -m abletools.cli validate build/racks-hazy
python -m abletools.cli drum-essentials --output build/drums-druiid --style DRUIID --seed 1842
python -m abletools.cli validate build/drums-druiid
python -m abletools.cli validate build/drums-druiid.zip
python -m abletools.cli drum-essentials --output build/drums-hazy --style HAZY --seed 1842
python -m abletools.cli validate build/drums-hazy
python -m abletools.cli validate build/drums-hazy.zip
```

## Change discipline

Prefer small, inspectable generators and validators. New asset formats require tests, documentation, and an explicit capability-gate update. Do not loosen validators merely to make a failing asset pass.
