"""Deterministic WAV synthesis and validation."""

from __future__ import annotations

import math
import wave
from pathlib import Path

from .capabilities import require_capability
from .seed import seeded_rng


def _pcm24(sample: float) -> bytes:
    value = max(-1.0, min(1.0, sample))
    integer = round(value * 8_388_607)
    if integer < 0:
        integer += 1 << 24
    return integer.to_bytes(3, "little", signed=False)


def write_kick_wav(
    path: str | Path,
    *,
    seed: int,
    duration: float = 0.8,
    sample_rate: int = 48_000,
) -> Path:
    """Render a compact mono kick as 24-bit PCM WAV."""
    require_capability("pcm_wav")
    if not 0.1 <= duration <= 4.0:
        raise ValueError("duration must be between 0.1 and 4.0 seconds")
    if sample_rate < 8_000:
        raise ValueError("sample_rate is too low")
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    rng = seeded_rng(seed, "kick-wav", {"duration": duration, "sample_rate": sample_rate})
    frame_count = round(duration * sample_rate)
    phase = 0.0
    samples: list[float] = []
    body_decay = 9.0 + rng.random() * 2.0
    start_frequency = 105.0 + rng.random() * 22.0
    end_frequency = 43.0 + rng.random() * 6.0

    for frame in range(frame_count):
        t = frame / sample_rate
        frequency = end_frequency + (start_frequency - end_frequency) * math.exp(-t * 35.0)
        phase += 2.0 * math.pi * frequency / sample_rate
        body = math.sin(phase) * math.exp(-t * body_decay)
        click_env = max(0.0, 1.0 - t / 0.012)
        click = (rng.random() * 2.0 - 1.0) * click_env * 0.18
        samples.append(math.tanh((body + click) * 1.35))

    peak = max(abs(sample) for sample in samples) or 1.0
    gain = 0.88 / peak
    frames = b"".join(_pcm24(sample * gain) for sample in samples)
    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(3)
        wav.setframerate(sample_rate)
        wav.writeframes(frames)
    return output


def validate_wav(path: str | Path) -> dict[str, int | float]:
    """Validate PCM WAV format and calculate sample peak."""
    require_capability("pcm_wav")
    with wave.open(str(path), "rb") as wav:
        if wav.getcomptype() != "NONE":
            raise ValueError("WAV must use uncompressed PCM")
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        frame_count = wav.getnframes()
        frames = wav.readframes(frame_count)
    if channels not in (1, 2) or sample_width not in (2, 3, 4):
        raise ValueError("unsupported WAV channel count or sample width")
    if sample_rate <= 0 or frame_count <= 0:
        raise ValueError("WAV contains no usable audio")

    peak_integer = 0
    for index in range(0, len(frames), sample_width):
        raw = frames[index : index + sample_width]
        value = int.from_bytes(raw, "little", signed=False)
        sign_bit = 1 << (sample_width * 8 - 1)
        if value & sign_bit:
            value -= 1 << (sample_width * 8)
        peak_integer = max(peak_integer, abs(value))
    full_scale = (1 << (sample_width * 8 - 1)) - 1
    peak = peak_integer / full_scale
    if peak > 1.0:
        raise ValueError("WAV exceeds integer full scale")
    return {
        "channels": channels,
        "sample_width_bits": sample_width * 8,
        "sample_rate": sample_rate,
        "frames": frame_count,
        "peak": round(peak, 6),
    }
