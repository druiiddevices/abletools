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

## Verification

Run before committing:

```bash
python -m unittest discover -s tests
python -m abletools.cli demo --output build/smoke --seed 1842
python -m abletools.cli validate build/smoke
```

## Change discipline

Prefer small, inspectable generators and validators. New asset formats require tests, documentation, and an explicit capability-gate update. Do not loosen validators merely to make a failing asset pass.
