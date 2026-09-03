# Abletools Work Local implementation handoff R2

The repository inspection and knowledge delta are complete. Do not repeat the inspection and do not restart the project.

## Sync first

Start from the latest remote `main` and confirm these files exist locally:

1. `AGENTS.md`
2. `docs/knowledge/KNOWLEDGE_ABLETON_ASSET_STANDARDS_R1.md`
3. `docs/knowledge/KNOWLEDGE_DRUIID_STYLE_R1.md`
4. `docs/knowledge/KNOWLEDGE_BOC_STYLE_R1.md`
5. `docs/knowledge/KNOWLEDGE_ABLETON_FX_RACKS_R1.md`

If any are missing, stop and report the current branch and `git status --short --branch`. Do not reconstruct them from memory.

## Accepted sequencing correction

Keep rack design separate from native rack serialization:

- A structured rack-blueprint contract, validator, and original sound-design catalog may be implemented before native export.
- Native `.adg`/`.adv` serialization remains disabled until fixture-based round-trip tests in Ableton Live pass.
- Never label a JSON or Markdown blueprint as a finished Ableton rack.
- Every sound-design rack family must have at least eight extensive, useful, premapped macros with documented multi-parameter targets, safe ranges, and Macro Variations. Use twelve to sixteen only when each added macro remains distinct and performance-worthy.

The planned order is now:

1. shared contract hardening plus DRUIID MIDI Essentials
2. separate HAZY MIDI Essentials
3. rack-blueprint contract and sound-design tool catalog
4. drums and general samples/loops
5. native rack fixture/export work when an Ableton validation path is available, followed by the remaining independently gated formats

## Implement milestone 1 now

Create a focused branch and implement a standards-compliant **DRUIID MIDI Essentials** vertical slice. This milestone must include:

- an explicit capability registry used by runtime code
- deterministic, canonical recipe inputs and profile routing for `DRUIID` only
- chord, bass, motif/arpeggio, and drum-pattern MIDI clips
- degree-first harmony, scale-aware pitch generation, separately controllable bass and upper voices, practical ranges, and related seeded A/B/C mutations
- complete per-asset metadata required by the standards file, including degree sequence and chord symbols where applicable
- strict MIDI checks for event ordering, balanced notes, zero-length notes, clip length, ranges, declared drum mapping, and trailing data
- strict manifest validation against the full schema, including version, file inventory, checksums, dependency data, and validation-record coverage
- a pack `README.md`
- deterministic ZIP writing and ZIP validation for path safety, manifest contents, checksums, and extracted MIDI
- tests proving identical inputs produce byte-identical MIDI, manifest, and ZIP outputs and that corrupt or unsafe packs fail

Use only standard-library or existing project dependencies unless a new dependency is clearly justified. Write generated artifacts only under `build/`. Keep `HAZY` generation, WAV expansion, samples, native rack files, Serum 2, grooves, Max for Live, and publication out of this pull request.

## Completion response

Run the repository verification commands from `AGENTS.md`, add focused negative tests, and open a pull request. Return:

1. the PR URL
2. a concise capability summary
3. exact tests and smoke commands run
4. any remaining limitations or native-format gates
