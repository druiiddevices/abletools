# Ableton sound-design and instrument racks R1

## Purpose

Treat Audio Effect Racks and Instrument Racks as first-class Abletools asset lanes. Audio Effect Racks are creative sound-design tools for transforming synths, drums, samples, atmospheres, Foley, and full musical parts. Instrument Racks provide playable sound sources with synthesis and downstream effects unified behind one performance surface. They are not limited to corrective mixing, mastering, or lightly wrapped factory presets.

Design original tools that are playable, fast to understand, and safe at useful settings. Prefer stock Ableton Live 12 devices unless the user requests and owns a third-party dependency.

## Blueprint versus native rack

Keep two capabilities separate:

1. A **rack blueprint** is a structured development specification describing topology, devices, mappings, ranges, variations, gain staging, and tests. It can be generated and validated without serializing an Ableton file.
2. A **native rack** is a real `.adg` that has opened successfully in the target Live version and passed mapping, dependency, signal-flow, and audio safety checks.

Blueprint work may be implemented early. Native `.adg` export remains gated until fixture-based round-trip testing exists. A JSON or Markdown blueprint is never a finished rack and is not a user-facing substitute unless the user explicitly accepts a manual build sheet.

## Rack design contract

Every blueprint should declare:

- rack name, role, style, version, and intended source material
- minimum Ableton Live version and all dependencies
- serial and parallel chain topology in left-to-right signal-flow order
- every device, important parameter value, and chain level/pan setting
- a dry/pass-through strategy and the behavior at the neutral default
- macro name, color, info text, default, minimum, maximum, polarity, curve, and all mapped targets
- each mapping target's full device/chain path, parameter, range, direction, and musical purpose
- whether each macro is excluded from randomization or Macro Variations
- named Macro Variations with a musical purpose
- input-level assumptions, output trim, gain-staging notes, latency, and tail behavior
- mono, stereo, low-frequency, clipping, bypass, and automation safety notes
- test signals and validation results; never invent a passed check

Every Abletools Audio Effect Rack and Instrument Rack must arrive with an extensive, fully premapped performance panel. Eight mapped macros is the minimum and 16 is the maximum. Target 8–12 for focused tools and 12–16 for deeper instruments or processors when every additional control remains distinct and useful. Do not ship empty placeholders, redundant controls, or macros mapped only for appearance. One macro should control several coordinated parameters when that creates a clear musical transformation, including inverted ranges where appropriate.

The macro panel should collectively cover:

- primary character or transformation intensity
- tonal or spectral focus
- motion or rhythmic behavior
- time, decay, or envelope behavior
- spatial or stereo behavior with low-frequency safety
- dry/wet or parallel blend
- explicit output trim
- at least one role-specific performance control

## Macro and variation rules

- Milestone 3A blueprints use linear mappings only. Normalize a macro position as
  `(x - macro.minimum) / (macro.maximum - macro.minimum)`; interpolate from target minimum to
  maximum for direct mappings and from maximum to minimum for inverse mappings.
- A target's declared neutral must be the value reached at the macro's neutral position. Integer
  controls use documented nearest-integer quantization; continuous controls must agree within the
  validator's numerical tolerance.
- `macro_variations.INIT` is the authoritative initial state. Every mapped device setting must equal
  the target value reconstructed from INIT.
- Within one rack, each device-path and parameter pair belongs to exactly one macro. Combine related
  concepts or select a different documented parameter instead of creating competing macro owners.
- Make the neutral default immediately usable and level-conscious.
- Give every macro one understandable performance concept rather than exposing engineering clutter.
- Favor coordinated multi-parameter mappings that make complex processing playable from the top level.
- Give each macro concise Info Text that explains what it changes and warns about any extreme behavior.
- Bound mappings so every edge state is intentional. Avoid dead zones, sudden dangerous level jumps, unstable feedback, and uncontrolled sub energy.
- Map an output trim when processing can add gain. Do not hide makeup gain inside an unrelated macro.
- Exclude safety-critical controls such as output level, limiter ceiling, and sub protection from randomization and variations when possible.
- Prefer three to five variations: `INIT`, `SUBTLE`, `ACTIVE`, `EXTREME_SAFE`, and an optional role-specific state.
- Variations must remain useful starting points, not novelty snapshots.
- For DRUIID racks, variations should form a related A/B/C family with bounded change.
- For HAZY racks, degradation should accumulate in layers while at least one dry or intelligible anchor remains.

## Initial Audio Effect Rack families

| Family | Purpose | Required baseline macro concepts |
|---|---|---|
| `AGE_MACHINE` | Controlled bandwidth loss, saturation, drift, dust, and worn-media color | AGE, DRIFT, DUST, FOCUS, WOW, BLOOM, WIDTH, OUT |
| `MEMORY_BLOOM` | Diffuse delay/reverb memory that can swell around a dry anchor | BLOOM, ECHO, SMEAR, TAIL, DUCK, TONE, WIDTH, OUT |
| `RHYTHM_FRACTURE` | Tempo-aware gating, repeats, stutters, and rhythmic rearrangement | RATE, GATE, REPEAT, OFFSET, MUTATE, TONE, MIX, OUT |
| `TRANSIENT_MUTATOR` | Reshape attack, body, crack, decay, dirt, and room character | ATTACK, BODY, CRACK, DECAY, DIRT, TONE, MIX, OUT |
| `RESONANT_PERCOLATOR` | Turn short sounds and Foley into tuned, playable resonant percussion | PITCH, TENSION, STRIKE, DECAY, DAMP, SPREAD, MIX, OUT |
| `SPECTRAL_SHADOW` | Create filtered doubles, spectral contrast, motion, and shadow layers | FOCUS, SHIFT, SMEAR, SHADOW, MOTION, AIR, MIX, OUT |
| `FOLEY_ANIMATOR` | Add grain, motion, filtering, pitch life, and space to static recordings | GRAIN, MOTION, DUST, FILTER, PITCH, SPACE, MIX, OUT |
| `BUILD_ENGINE` | Generate controlled risers, pressure, density, widening, and transition tails | RISE, PRESSURE, PITCH, DENSITY, SPACE, IMPACT, MIX, OUT |
| `BASS_MUTATOR` | Add weight, controlled growl, movement, and upper-band width without losing the center | WEIGHT, GROWL, MOTION, DIRT, FOCUS, WIDTH_HI, MIX, OUT |
| `DRUM_MUTATION_BUS` | Turn a loop or kit into related punch, crush, room, dust, and motion states | PUNCH, CRUSH, SMACK, ROOM, DUST, MOTION, MIX, OUT |

Each family must implement all eight baseline macro concepts or document a clearly superior role-specific replacement. Expanding a rack to twelve or sixteen macros is encouraged when the extra controls expose genuinely independent performance dimensions. The family name is a role, not a fixed recipe. DRUIID and HAZY variants must use their own style profile and should not be produced by relabeling identical mappings.

## Operator Instrument Racks

Build original Instrument Racks around Ableton Operator as a dedicated stock-instrument lane. Operator provides four oscillators, FM/additive/subtractive relationships, multiple algorithms, individual oscillator envelopes, an LFO, a filter, pitch controls, glide, spread, and global performance settings. Use that architecture deliberately instead of treating Operator as a hidden preset host.

An Operator Instrument Rack must declare and validate:

- the Operator algorithm, oscillator waveforms, levels, ratios or fixed frequencies, and oscillator envelopes
- filter type, cutoff, resonance, drive or morph behavior, filter envelope, and key/velocity tracking
- LFO waveform, rate, sync mode, retrigger behavior, depth, and destinations
- pitch envelope, transpose, glide, spread, voices, velocity response, and any controller mappings
- optional MIDI effects before Operator and stock audio effects after Operator in valid signal-flow order
- complete post-instrument effects topology, settings, dry/wet behavior, gain staging, and tail behavior
- 8–16 top-level macros spanning synthesis, articulation, modulation, effects, spatial behavior, and output
- at least one coordinated macro that morphs Operator and downstream effects together
- named Macro Variations that expose genuinely different but related playable states

Do not map every Operator parameter merely to inflate the control count. “Fully mapped” means the rack exposes all musically important performance dimensions while deeper calibration values remain safely set inside the rack.

### Initial Operator instrument families

| Family | Role | Required baseline macro concepts |
|---|---|---|
| `OPERATOR_SUB_FORM` | Focused sub, FM, and mid-bass instrument | BODY, FM, SUB, BITE, FILTER, ENV, GLIDE, MOTION, DIRT, SPACE, WIDTH_HI, OUT |
| `OPERATOR_GHOST_LEAD` | Expressive mono/poly lead with controlled instability | SHAPE, FM, EDGE, FILTER, ATTACK, RELEASE, GLIDE, VIBRATO, ECHO, BLOOM, WIDTH, OUT |
| `OPERATOR_MEMORY_PAD` | Slow harmonic pad with animated color and space | COLOR, FM, HARMONICS, FILTER, ATTACK, RELEASE, DRIFT, MOTION, AGE, BLOOM, WIDTH, OUT |
| `OPERATOR_GLASS_BELL` | Bell, mallet, and metallic key instrument | STRIKE, METAL, RATIO, TUNE, DECAY, DAMP, MOTION, AGE, ECHO, BLOOM, WIDTH, OUT |
| `OPERATOR_RESONANT_PERC` | Tuned percussion with synthetic body and transient control | PITCH, SNAP, BODY, NOISE, TENSION, DECAY, FILTER, MOTION, DIRT, ROOM, WIDTH, OUT |
| `OPERATOR_ATMO_DRONE` | Tonal atmosphere and evolving drone source | ROOT, HARMONICS, FM, FILTER, DRIFT, MOTION, DENSITY, DUST, SHADOW, BLOOM, WIDTH, OUT |

Create DRUIID and HAZY variants where musically appropriate. They must differ in synthesis architecture, modulation behavior, effects, and macro ranges—not just names or variation values.

## Style behavior

### DRUIID

- Keep timbre neutral and production-ready until the user supplies enough Druiid audio evidence.
- Express identity through deterministic blueprint generation, clear macro relationships, bounded mutation, tempo-aware modulation, and related A/B/C variations.
- Useful controls include MUTATE, MOTION, TENSION, DENSITY, SPREAD, and an optional AGE dimension.
- Do not invent an organic, occult, woodland, or dark timbral mythology.

### HAZY

- Favor controlled drift, softened bandwidth, layered saturation, filtered noise, spatial memory, asymmetrical echoes, and restrained spectral wear.
- Useful controls include AGE, DRIFT, FOCUS, BLOOM, SHADOW, MOTION, DUST, and WIDTH.
- Preserve clarity, low-end stability, and an intelligible anchor as degradation increases.
- Create original behavior; do not reproduce a recognizable artist preset or song effect.

## Validation boundary

Blueprint validation can confirm schema completeness, known device identifiers, mapping ranges, topology, dependencies, deterministic output, naming, and test declarations. It cannot prove that a rack opens or sounds correct in Ableton Live.

Native approval requires a real Live fixture or controlled manual test that confirms:

- the `.adg` opens in the declared Live version
- stock and third-party dependencies resolve exactly as declared
- devices, chains, and mappings survive save/reopen
- every macro moves the intended parameters across the declared range
- every advertised macro is mapped, useful, documented, and free of dangerous discontinuities
- Macro Variations recall correctly
- dry/wet, bypass, automation, mono, stereo, low-end, clipping, tail, and latency behavior is acceptable
- the rack produces a genuinely useful result on its declared source types
- an Instrument Rack plays across its declared note and velocity range without unsafe output, stuck notes, unintended pitch discontinuities, or broken voice behavior
- Operator settings, upstream MIDI effects, downstream audio effects, and top-level mappings survive save/reopen exactly

Until those checks exist, keep `native_ableton_rack_export` disabled.

## Primary references

- [Ableton Live 12: Instrument, Drum and Effect Racks](https://www.ableton.com/en/manual/instrument-drum-and-effect-racks/)
- [Ableton Live 12: Operator](https://www.ableton.com/en/manual/live-instrument-reference/#operator)
