"""
Podcast TTS core — shared synthesis + stitching pipeline.

Engine: Kokoro fp16 (ONNX), CPU. Weights fetched at runtime from a GitHub
release (the only host reachable from the claude.ai sandbox allowlist) and
cached so repeat runs in the same session skip the download.

This module is deliberately wrapper-agnostic: the same code runs behind the
Claude skill and the GitHub Actions template. It knows nothing about either.
"""

import json
import os
import subprocess
import sys
import time
import urllib.request

import numpy as np
import soundfile as sf

# --- Weight sources (GitHub release assets: allowlisted in the sandbox) ---
RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
MODEL_URL = f"{RELEASE}/kokoro-v1.0.fp16.onnx"   # fp16: fastest on 1-core CPU, ~170MB
VOICES_URL = f"{RELEASE}/voices-v1.0.bin"        # ~27MB

CACHE_DIR = os.environ.get("PODCAST_CACHE", os.path.expanduser("~/.cache/podcast-tts"))
MODEL_PATH = os.path.join(CACHE_DIR, "kokoro-v1.0.fp16.onnx")
VOICES_PATH = os.path.join(CACHE_DIR, "voices-v1.0.bin")

# --- Voice registry: friendly names -> Kokoro voice IDs ---
# Defaults are British F + British M. lang is always en-gb for these.
VOICES = {
    "emma": "bf_emma",      # British female (default host A)
    "george": "bm_george",  # British male   (default host B)
    "alice": "bf_alice",    # British female (alt)
    "lily": "bf_lily",      # British female (alt)
    "daniel": "bm_daniel",  # British male   (alt)
    "lewis": "bm_lewis",    # British male   (alt)
}
DEFAULT_SPEAKERS = ["emma", "george"]  # first-seen -> emma, second -> george

GAP_SECONDS = 0.4   # silence inserted between turns
SAMPLE_RATE = 24000  # Kokoro native


def _download(url, dest):
    tmp = dest + ".part"
    with urllib.request.urlopen(url, timeout=180) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length", 0))
        got = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if total:
                pct = 100 * got / total
                print(f"  ...{pct:5.1f}%  ({got >> 20}/{total >> 20} MB)", flush=True)
    os.replace(tmp, dest)


def ensure_weights():
    """Fetch model + voices into the cache if not already present."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    if not os.path.exists(MODEL_PATH):
        print("Fetching voice model (~170MB, first run only)...", flush=True)
        _download(MODEL_URL, MODEL_PATH)
    if not os.path.exists(VOICES_PATH):
        print("Fetching voice pack (~27MB, first run only)...", flush=True)
        _download(VOICES_URL, VOICES_PATH)
    return MODEL_PATH, VOICES_PATH


def load_engine():
    from kokoro_onnx import Kokoro
    model, voices = ensure_weights()
    return Kokoro(model, voices)


def resolve_voice(name):
    """Accept a friendly name, a raw Kokoro ID, or fall back to a default."""
    key = name.strip().lower()
    if key in VOICES:
        return VOICES[key]
    if key.startswith(("bf_", "bm_", "af_", "am_")):
        return key  # already a raw voice ID
    return None


def assign_voices(turns):
    """
    Map speaker labels in the script to voices.
    turns: list of {"speaker": str, "text": str, "voice": optional str}
    Speakers are assigned in first-seen order to the default British pair.
    An explicit "voice" on a turn overrides the default for that speaker.
    Returns the turns with a resolved "voice_id" on each, plus a mapping.
    """
    mapping = {}
    order = []
    for t in turns:
        spk = t["speaker"]
        if spk not in mapping:
            order.append(spk)
            explicit = t.get("voice")
            if explicit and resolve_voice(explicit):
                mapping[spk] = resolve_voice(explicit)
            else:
                default_name = DEFAULT_SPEAKERS[(len(order) - 1) % len(DEFAULT_SPEAKERS)]
                mapping[spk] = VOICES[default_name]
    for t in turns:
        t["voice_id"] = mapping[t["speaker"]]
    return turns, mapping


def synthesise(turns, out_path, engine=None, progress_path=None):
    """
    Synthesise each turn and stitch into one file.
    Writes progress to progress_path (JSON) after each turn so a polling
    wrapper can report status without blocking on the whole run.
    """
    if engine is None:
        engine = load_engine()
    turns, mapping = assign_voices(turns)
    total = len(turns)
    clips = []
    gap = np.zeros(int(SAMPLE_RATE * GAP_SECONDS), dtype=np.float32)
    started = time.time()

    def report(done, state="running"):
        if not progress_path:
            return
        audio_s = sum(len(c) for c in clips) / SAMPLE_RATE
        with open(progress_path, "w") as f:
            json.dump({
                "state": state,
                "turns_done": done,
                "turns_total": total,
                "audio_seconds": round(audio_s, 1),
                "elapsed_seconds": round(time.time() - started, 1),
            }, f)

    for i, t in enumerate(turns):
        samples, sr = engine.create(t["text"], voice=t["voice_id"], speed=1.0, lang="en-gb")
        clips.append(samples.astype(np.float32))
        if i < total - 1:
            clips.append(gap)
        report(i + 1)

    audio = np.concatenate(clips)
    # If mp3 requested, write a temp wav then transcode (podcast-friendly, ~10x smaller).
    if out_path.lower().endswith(".mp3"):
        wav_tmp = out_path[:-4] + ".tmp.wav"
        sf.write(wav_tmp, audio, SAMPLE_RATE)
        subprocess.run(
            ["ffmpeg", "-y", "-i", wav_tmp, "-codec:a", "libmp3lame",
             "-qscale:a", "2", out_path],
            check=True, capture_output=True,
        )
        os.remove(wav_tmp)
    else:
        sf.write(out_path, audio, SAMPLE_RATE)
    report(total, state="done")
    return {
        "out_path": out_path,
        "duration_seconds": round(len(audio) / SAMPLE_RATE, 1),
        "turns": total,
        "voice_mapping": mapping,
        "elapsed_seconds": round(time.time() - started, 1),
    }


if __name__ == "__main__":
    # CLI: core.py <turns.json> <out.wav> [progress.json]
    with open(sys.argv[1]) as f:
        turns = json.load(f)
    out = sys.argv[2] if len(sys.argv) > 2 else "podcast.wav"
    prog = sys.argv[3] if len(sys.argv) > 3 else None
    result = synthesise(turns, out, progress_path=prog)
    print(json.dumps(result, indent=2))
