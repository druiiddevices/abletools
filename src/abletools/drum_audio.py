"""Original deterministic drum synthesis and strict canonical WAV validation."""

from __future__ import annotations

import io
import hashlib
import math
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .capabilities import require_capability
from .drum_recipe import (
    BIT_DEPTH,
    CHANNELS,
    DRUM_FAMILY_SPECS,
    PREVIEW_DURATION_BOUNDS,
    SAMPLE_RATE,
    DrumVoiceRecipe,
)
from .seed import seeded_rng

MAX_PEAK = 0.92
MIN_PEAK = 0.08
MIN_RMS = 0.004
MAX_DC_OFFSET = 0.003
SILENCE_THRESHOLD = 0.001
MAX_EDGE_SILENCE_FRAMES = 480
PCM24_SCALE = 8_388_607


@dataclass(frozen=True)
class DrumRender:
    """Rendered normalized samples plus the parameters that created them."""

    samples: tuple[float, ...]
    synthesis_parameters: dict[str, Any]


def _bounded(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _lerp(minimum: float, maximum: float, amount: float) -> float:
    return minimum + (maximum - minimum) * amount


def _duration(recipe: DrumVoiceRecipe, random_amount: float) -> float:
    spec = DRUM_FAMILY_SPECS[recipe.family]
    profile = recipe.pack.profile
    character = recipe.pack.character_for(recipe.family)
    center = {
        "kick": 0.55,
        "snare": 0.48,
        "closed_hat": 0.42,
        "open_hat": 0.55,
        "shaker": 0.46,
        "percussion": 0.50,
    }[recipe.family]
    amount = _bounded((center + (random_amount - 0.5) * 0.38 + (character - 0.5) * 0.16) * profile.tail_scale, 0.08, 0.94)
    return round(_lerp(spec.minimum_duration, spec.maximum_duration, amount), 6)


def _noise_highpass(value: float, previous: float) -> tuple[float, float]:
    return value - previous * 0.92, value


def _render_kick(recipe: DrumVoiceRecipe, rng: Any, frames: int) -> tuple[list[float], dict[str, Any]]:
    profile = recipe.pack.profile
    character = recipe.pack.character_for("kick")
    start_hz = 104.0 + rng.random() * 54.0 + character * 12.0
    end_hz = 40.0 + rng.random() * 16.0
    pitch_decay = 27.0 + rng.random() * 23.0
    body_decay = 6.5 + rng.random() * 5.0 + profile.transient_sharpness * 1.8
    click_mix = 0.07 + rng.random() * 0.13 + profile.brightness * 0.05
    harmonic_mix = 0.05 + rng.random() * 0.12
    phase = 0.0
    prior_noise = 0.0
    samples: list[float] = []
    for frame in range(frames):
        t = frame / SAMPLE_RATE
        frequency = end_hz + (start_hz - end_hz) * math.exp(-t * pitch_decay)
        phase += math.tau * frequency / SAMPLE_RATE
        envelope = math.exp(-t * body_decay)
        body = math.sin(phase) * envelope
        harmonic = math.sin(phase * 2.0 + 0.18) * envelope * harmonic_mix
        raw_noise = rng.random() * 2.0 - 1.0
        click, prior_noise = _noise_highpass(raw_noise, prior_noise)
        click *= max(0.0, 1.0 - t / (0.006 + (1.0 - profile.transient_sharpness) * 0.006)) * click_mix
        samples.append(body + harmonic + click)
    return samples, {
        "body_decay": round(body_decay, 6),
        "click_mix": round(click_mix, 6),
        "end_frequency_hz": round(end_hz, 6),
        "harmonic_mix": round(harmonic_mix, 6),
        "pitch_decay": round(pitch_decay, 6),
        "start_frequency_hz": round(start_hz, 6),
        "voice_model": "pitched_body_transient_v1",
    }


def _render_snare(recipe: DrumVoiceRecipe, rng: Any, frames: int) -> tuple[list[float], dict[str, Any]]:
    profile = recipe.pack.profile
    character = recipe.pack.character_for("snare")
    body_hz = 150.0 + rng.random() * 105.0 + character * 20.0
    body_decay = 13.0 + rng.random() * 9.0
    noise_decay = 8.0 + rng.random() * 8.0 + profile.transient_sharpness * 2.0
    noise_mix = 0.48 + rng.random() * 0.24
    transient_mix = 0.12 + rng.random() * 0.13
    phase = rng.random() * math.tau
    second_phase = rng.random() * math.tau
    prior_noise = 0.0
    samples: list[float] = []
    for frame in range(frames):
        t = frame / SAMPLE_RATE
        phase += math.tau * body_hz / SAMPLE_RATE
        second_phase += math.tau * (body_hz * (1.51 + character * 0.08)) / SAMPLE_RATE
        tonal = (math.sin(phase) + 0.42 * math.sin(second_phase)) * math.exp(-t * body_decay)
        raw_noise = rng.random() * 2.0 - 1.0
        bright_noise, prior_noise = _noise_highpass(raw_noise, prior_noise)
        noise = bright_noise * math.exp(-t * noise_decay) * noise_mix
        transient = bright_noise * max(0.0, 1.0 - t / 0.009) * transient_mix
        samples.append(tonal * 0.46 + noise + transient)
    return samples, {
        "body_decay": round(body_decay, 6),
        "body_frequency_hz": round(body_hz, 6),
        "noise_decay": round(noise_decay, 6),
        "noise_mix": round(noise_mix, 6),
        "transient_mix": round(transient_mix, 6),
        "voice_model": "tonal_noise_layer_v1",
    }


def _render_hat(recipe: DrumVoiceRecipe, rng: Any, frames: int) -> tuple[list[float], dict[str, Any]]:
    profile = recipe.pack.profile
    is_open = recipe.family == "open_hat"
    character = recipe.pack.character_for(recipe.family)
    base_hz = 4_300.0 + rng.random() * 1_900.0 + profile.brightness * 900.0
    ratios = (1.0, 1.327, 1.713, 2.091, 2.447)
    phases = [rng.random() * math.tau for _ in ratios]
    metallic_mix = 0.38 + rng.random() * 0.25
    decay = (4.8 + rng.random() * 3.2) if is_open else (22.0 + rng.random() * 18.0)
    decay *= 1.08 - character * 0.12
    prior_noise = 0.0
    samples: list[float] = []
    for frame in range(frames):
        t = frame / SAMPLE_RATE
        envelope = math.exp(-t * decay)
        metallic = 0.0
        for index, ratio in enumerate(ratios):
            phases[index] += math.tau * base_hz * ratio / SAMPLE_RATE
            metallic += math.sin(phases[index])
        metallic /= len(ratios)
        raw_noise = rng.random() * 2.0 - 1.0
        bright_noise, prior_noise = _noise_highpass(raw_noise, prior_noise)
        edge = max(0.0, 1.0 - t / 0.005) * 0.16 * profile.transient_sharpness
        samples.append((metallic * metallic_mix + bright_noise * (0.54 + edge)) * envelope)
    return samples, {
        "base_frequency_hz": round(base_hz, 6),
        "decay": round(decay, 6),
        "envelope": "open" if is_open else "closed",
        "metallic_mix": round(metallic_mix, 6),
        "oscillator_ratios": list(ratios),
        "voice_model": "inharmonic_noise_hat_v1",
    }


def _render_shaker(recipe: DrumVoiceRecipe, rng: Any, frames: int) -> tuple[list[float], dict[str, Any]]:
    profile = recipe.pack.profile
    character = recipe.pack.character_for("shaker")
    event_count = 7 + recipe.variant + round(character * 5)
    positions = [0]
    for index in range(1, event_count):
        nominal = index * (frames - 1) / event_count
        jitter = (rng.random() - 0.5) * frames / event_count * 0.42
        positions.append(max(0, min(frames - 1, round(nominal + jitter))))
    positions = sorted(set(positions))
    amplitudes = {position: 0.35 + rng.random() * 0.65 for position in positions}
    decay = 110.0 + rng.random() * 105.0
    grain = 0.0
    prior_noise = 0.0
    samples: list[float] = []
    for frame in range(frames):
        if frame in amplitudes:
            grain += amplitudes[frame]
        grain *= math.exp(-decay / SAMPLE_RATE)
        raw_noise = rng.random() * 2.0 - 1.0
        bright_noise, prior_noise = _noise_highpass(raw_noise, prior_noise)
        wobble = 1.0 + (0.025 if recipe.pack.style == "DRUIID" else 0.075) * math.sin(
            math.tau * (3.0 + recipe.variant * 0.23) * frame / SAMPLE_RATE
        )
        samples.append(bright_noise * grain * wobble * (0.58 + profile.brightness * 0.24))
    return samples, {
        "event_count": len(positions),
        "event_positions_frames": positions,
        "grain_decay": round(decay, 6),
        "timing_model": "seeded_bounded_grains_v1",
        "voice_model": "stochastic_grain_shaker_v1",
    }


def _render_percussion(recipe: DrumVoiceRecipe, rng: Any, frames: int) -> tuple[list[float], dict[str, Any]]:
    profile = recipe.pack.profile
    models = ("tonal", "metallic", "wooden", "membrane", "synthetic", "clave", "bell", "impact")
    model = models[recipe.variant - 1]
    character = recipe.pack.character_for("percussion")
    fundamental = 155.0 + recipe.variant * 47.0 + rng.random() * 72.0
    decay = 7.0 + rng.random() * 20.0
    ratios_by_model = {
        "tonal": (1.0, 2.0),
        "metallic": (1.0, 1.411, 2.197),
        "wooden": (1.0, 2.73),
        "membrane": (1.0, 1.59),
        "synthetic": (1.0, 1.25, 3.07),
        "clave": (1.0, 3.11),
        "bell": (1.0, 2.42, 3.86),
        "impact": (1.0, 1.71, 2.89),
    }
    ratios = ratios_by_model[model]
    phases = [rng.random() * math.tau for _ in ratios]
    noise_mix = 0.05 + (0.18 if model in {"wooden", "impact", "membrane"} else 0.07) * rng.random()
    samples: list[float] = []
    prior_noise = 0.0
    for frame in range(frames):
        t = frame / SAMPLE_RATE
        envelope = math.exp(-t * decay)
        tone = 0.0
        for index, ratio in enumerate(ratios):
            bend = 1.0 + (0.035 * math.exp(-t * 20.0) if model in {"membrane", "synthetic"} else 0.0)
            phases[index] += math.tau * fundamental * ratio * bend / SAMPLE_RATE
            tone += math.sin(phases[index]) / (index + 1)
        tone /= sum(1.0 / (index + 1) for index in range(len(ratios)))
        raw_noise = rng.random() * 2.0 - 1.0
        edge_noise, prior_noise = _noise_highpass(raw_noise, prior_noise)
        transient = edge_noise * max(0.0, 1.0 - t / (0.007 + character * 0.004)) * noise_mix
        samples.append(tone * envelope + transient * (0.7 + profile.transient_sharpness * 0.4))
    return samples, {
        "decay": round(decay, 6),
        "fundamental_hz": round(fundamental, 6),
        "model": model,
        "noise_mix": round(noise_mix, 6),
        "ratios": list(ratios),
        "voice_model": "hybrid_percussion_v1",
    }


def _highpass(samples: Iterable[float], coefficient: float = 0.995) -> list[float]:
    previous_input = 0.0
    previous_output = 0.0
    result: list[float] = []
    for sample in samples:
        output = sample - previous_input + coefficient * previous_output
        result.append(output)
        previous_input = sample
        previous_output = output
    return result


def _lowpass(samples: Iterable[float], coefficient: float) -> list[float]:
    state = 0.0
    result: list[float] = []
    for sample in samples:
        state += coefficient * (sample - state)
        result.append(state)
    return result


def _finish(samples: list[float], recipe: DrumVoiceRecipe) -> list[float]:
    profile = recipe.pack.profile
    result = _highpass(samples)
    if recipe.pack.style == "HAZY":
        result = _lowpass(result, 0.24 + profile.brightness * 0.18)
    drive = 1.0 + profile.saturation * 1.8
    asymmetry = profile.asymmetry * 0.08
    result = [math.tanh((sample + asymmetry * sample * sample) * drive) for sample in result]
    mean = sum(result) / len(result)
    result = [sample - mean for sample in result]
    natural_peak = max(abs(sample) for sample in result)
    activity_threshold = max(0.0001, natural_peak * 0.006)
    last_active = max(
        (index for index, sample in enumerate(result) if abs(sample) > activity_threshold),
        default=0,
    )
    minimum_frames = math.ceil(DRUM_FAMILY_SPECS[recipe.family].minimum_duration * SAMPLE_RATE)
    result = result[: max(minimum_frames, last_active + 1)]
    trimmed_mean = sum(result) / len(result)
    result = [sample - trimmed_mean for sample in result]
    attack_frames = 64 if recipe.pack.style == "DRUIID" else 128
    end_frames = 192 if recipe.pack.style == "DRUIID" else 360
    final_index = len(result) - 1
    fade_window: list[float] = []
    for index in range(len(result)):
        factor = 1.0
        if index < attack_frames:
            factor *= index / attack_frames
        if index > final_index - end_frames:
            factor *= (final_index - index) / end_frames
        result[index] *= factor
        fade_window.append(factor)
    residual_mean = sum(result) / len(result)
    window_mean = sum(fade_window) / len(fade_window)
    result = [
        sample - residual_mean * factor / window_mean
        for sample, factor in zip(result, fade_window)
    ]
    peak = max(abs(sample) for sample in result)
    if not math.isfinite(peak) or peak <= 0.0:
        raise ValueError("drum synthesis produced invalid or silent samples")
    target = profile.target_peak - recipe.variant * 0.002
    gain = target / peak
    return [sample * gain for sample in result]


def render_drum_voice(recipe: DrumVoiceRecipe) -> DrumRender:
    """Render one original drum voice from a fully isolated RNG namespace."""
    require_capability("pcm_wav")
    rng = seeded_rng(
        recipe.pack.seed,
        f"drum-one-shot:{recipe.pack.style}:{recipe.family}:{recipe.variant}",
        recipe.seed_data(),
    )
    duration = _duration(recipe, rng.random())
    frames = round(duration * SAMPLE_RATE)
    if recipe.family == "kick":
        raw, parameters = _render_kick(recipe, rng, frames)
    elif recipe.family == "snare":
        raw, parameters = _render_snare(recipe, rng, frames)
    elif recipe.family in {"closed_hat", "open_hat"}:
        raw, parameters = _render_hat(recipe, rng, frames)
    elif recipe.family == "shaker":
        raw, parameters = _render_shaker(recipe, rng, frames)
    else:
        raw, parameters = _render_percussion(recipe, rng, frames)
    finished = _finish(raw, recipe)
    parameters.update(
        {
            "character": recipe.pack.character_for(recipe.family),
            "duration_seconds": round(len(finished) / SAMPLE_RATE, 6),
            "post_process": "dc_block_fades_headroom_v1",
            "style_profile": recipe.pack.profile.description,
        }
    )
    return DrumRender(tuple(finished), parameters)


def _pcm24(sample: float) -> bytes:
    if not math.isfinite(sample):
        raise ValueError("PCM samples must be finite")
    if not -1.0 <= sample <= 1.0:
        raise ValueError("PCM sample exceeds full scale")
    integer = round(sample * PCM24_SCALE)
    if integer < 0:
        integer += 1 << BIT_DEPTH
    return integer.to_bytes(3, "little", signed=False)


def encode_pcm24_mono(samples: Iterable[float], sample_rate: int = SAMPLE_RATE) -> bytes:
    """Encode a canonical mono 24-bit PCM RIFF/WAVE byte stream."""
    if sample_rate != SAMPLE_RATE:
        raise ValueError("Drum Essentials WAVs require 48 kHz")
    sample_list = list(samples)
    if not sample_list:
        raise ValueError("cannot encode an empty WAV")
    frames = b"".join(_pcm24(sample) for sample in sample_list)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(BIT_DEPTH // 8)
        wav.setframerate(sample_rate)
        wav.writeframes(frames)
    return buffer.getvalue()


def write_pcm24_mono(path: str | Path, samples: Iterable[float]) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(encode_pcm24_mono(samples))
    return output


def write_drum_voice(path: str | Path, recipe: DrumVoiceRecipe) -> tuple[Path, DrumRender]:
    render = render_drum_voice(recipe)
    return write_pcm24_mono(path, render.samples), render


def read_pcm24_mono(path: str | Path) -> tuple[list[float], dict[str, int]]:
    """Read only the canonical WAV representation emitted by this milestone."""
    source = Path(path)
    data = source.read_bytes()
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("malformed PCM WAV header")
    if int.from_bytes(data[4:8], "little") + 8 != len(data):
        raise ValueError("malformed or truncated PCM WAV container")
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            if wav.getcomptype() != "NONE":
                raise ValueError("WAV must use uncompressed PCM")
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            sample_rate = wav.getframerate()
            frames = wav.getnframes()
            payload = wav.readframes(frames)
    except (EOFError, wave.Error) as error:
        raise ValueError("malformed or truncated PCM WAV") from error
    if (channels, sample_width, sample_rate) != (CHANNELS, BIT_DEPTH // 8, SAMPLE_RATE):
        raise ValueError("Drum Essentials WAV must be mono 48 kHz, 24-bit PCM")
    if len(data) != 44 + frames * sample_width or len(payload) != frames * sample_width:
        raise ValueError("malformed or truncated PCM WAV payload")
    samples: list[float] = []
    for index in range(0, len(payload), sample_width):
        integer = int.from_bytes(payload[index : index + sample_width], "little", signed=False)
        if integer & (1 << (BIT_DEPTH - 1)):
            integer -= 1 << BIT_DEPTH
        sample = integer / PCM24_SCALE
        if not math.isfinite(sample):
            raise ValueError("WAV contains invalid samples")
        samples.append(sample)
    return samples, {
        "channels": channels,
        "frames": frames,
        "sample_rate": sample_rate,
        "sample_width_bits": sample_width * 8,
    }


def _edge_silence(samples: list[float]) -> tuple[int, int]:
    leading = 0
    for sample in samples:
        if abs(sample) > SILENCE_THRESHOLD:
            break
        leading += 1
    trailing = 0
    for sample in reversed(samples):
        if abs(sample) > SILENCE_THRESHOLD:
            break
        trailing += 1
    return leading, trailing


def normalized_shape_sha256(samples: list[float]) -> str:
    """Hash normalized waveform shape so gain-only duplicates have one identity."""
    peak = max(abs(sample) for sample in samples)
    if peak <= 0.0:
        return hashlib.sha256(b"").hexdigest()
    digest = hashlib.sha256()
    for sample in samples:
        quantized = round(sample / peak * 127)
        digest.update(quantized.to_bytes(1, "little", signed=True))
    return digest.hexdigest()


def validate_drum_wav(path: str | Path, *, family: str) -> dict[str, int | float | str]:
    """Fail closed on format, level, boundary, silence, DC, and duration defects."""
    require_capability("pcm_wav")
    if family == "preview":
        duration_bounds = PREVIEW_DURATION_BOUNDS
    else:
        try:
            spec = DRUM_FAMILY_SPECS[family]
        except KeyError as error:
            raise ValueError(f"unknown drum family: {family}") from error
        duration_bounds = (spec.minimum_duration, spec.maximum_duration)
    samples, format_info = read_pcm24_mono(path)
    duration = len(samples) / SAMPLE_RATE
    if not duration_bounds[0] <= duration <= duration_bounds[1]:
        raise ValueError(f"{family} WAV duration is outside its family-specific range")
    peak = max(abs(sample) for sample in samples)
    rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
    dc_offset = sum(samples) / len(samples)
    if peak >= 1.0:
        raise ValueError("WAV clips at integer full scale")
    if peak > MAX_PEAK:
        raise ValueError("WAV has insufficient headroom")
    if peak < MIN_PEAK or rms < MIN_RMS:
        raise ValueError("WAV is silent or near-silent")
    if abs(dc_offset) > MAX_DC_OFFSET:
        raise ValueError("WAV has excessive DC offset")
    leading, trailing = _edge_silence(samples)
    if leading > MAX_EDGE_SILENCE_FRAMES or trailing > MAX_EDGE_SILENCE_FRAMES:
        raise ValueError("WAV has excessive leading or trailing silence")
    edge_window = min(8, len(samples))
    if (
        abs(samples[0]) > 1.0 / PCM24_SCALE
        or abs(samples[-1]) > 1.0 / PCM24_SCALE
        or max(abs(sample) for sample in samples[:edge_window]) > peak * 0.16
        or max(abs(sample) for sample in samples[-edge_window:]) > peak * 0.16
    ):
        raise ValueError("WAV is missing intentional boundary fades")
    if max(abs(samples[index] - samples[index - 1]) for index in range(1, edge_window)) > peak * 0.30:
        raise ValueError("WAV has a discontinuous onset boundary")
    if max(abs(samples[-index] - samples[-index - 1]) for index in range(1, edge_window)) > peak * 0.30:
        raise ValueError("WAV has a discontinuous end boundary")
    return {
        **format_info,
        "audio_shape_sha256": normalized_shape_sha256(samples),
        "dc_offset": round(dc_offset, 8),
        "duration_seconds": round(duration, 6),
        "leading_silence_ms": round(leading * 1000.0 / SAMPLE_RATE, 6),
        "peak": round(peak, 8),
        "rms": round(rms, 8),
        "trailing_silence_ms": round(trailing * 1000.0 / SAMPLE_RATE, 6),
    }


def render_preview(
    sources: Mapping[str, list[float]], placements: list[dict[str, Any]]
) -> tuple[float, ...]:
    """Assemble an audition preview solely by mixing declared source one-shots."""
    if not placements:
        raise ValueError("preview requires source placements")
    end_frame = 0
    for placement in placements:
        source = placement.get("source")
        start_frame = placement.get("start_frame")
        gain = placement.get("gain")
        if source not in sources:
            raise ValueError("preview placement references a missing source")
        if isinstance(start_frame, bool) or not isinstance(start_frame, int) or start_frame < 0:
            raise ValueError("preview start_frame must be a non-negative integer")
        if isinstance(gain, bool) or not isinstance(gain, (int, float)) or not 0.0 < gain <= 1.0:
            raise ValueError("preview gain must be between zero and one")
        end_frame = max(end_frame, start_frame + len(sources[source]))
    mix = [0.0] * end_frame
    for placement in placements:
        source_samples = sources[placement["source"]]
        start = placement["start_frame"]
        gain = float(placement["gain"])
        for offset, sample in enumerate(source_samples):
            mix[start + offset] += sample * gain
    peak = max(abs(sample) for sample in mix)
    if peak <= 0.0:
        raise ValueError("preview mix is silent")
    gain = 0.82 / peak
    mix = [sample * gain for sample in mix]
    fade_frames = min(240, len(mix) - 1)
    for index in range(fade_frames):
        mix[index] *= index / fade_frames
        mix[-index - 1] *= index / fade_frames
    return tuple(mix)


def write_preview(
    path: str | Path,
    sources: Mapping[str, list[float]],
    placements: list[dict[str, Any]],
) -> Path:
    return write_pcm24_mono(path, render_preview(sources, placements))
