# ClodCaster (Claude skill)

A Claude skill that turns a script — in *any* format — into podcast-style audio
with distinct neural voices. No API keys, no external services: speech is
generated on CPU inside Claude's environment using
[Kokoro](https://github.com/thewh1teagle/kokoro-onnx) (fp16 ONNX).

Two British hosts by default (female + male), clean turn-taking, output as a
downloadable `.mp3`.

## Install

Add this skill to your Claude environment (skills folder / capabilities that
support `SKILL.md`-based skills). The three files are:

- `SKILL.md` — instructions Claude follows.
- `scripts/core.py` — synthesis + stitching engine (fetches voice weights on
  first use, ~197MB, then caches them).
- `scripts/run.py` — background runner so long episodes don't hit execution
  time limits.

Dependencies (`kokoro-onnx`, `soundfile`, plus `ffmpeg`) are installed by Claude
at runtime as needed.

## Use

Give Claude a script in whatever shape you have — a rough dialogue, an interview
transcript, notes, an outline — and ask for a podcast. Claude will:

1. Normalise it into tagged speaker turns.
2. Show you the interpretation and the voices, and confirm before synthesising.
3. Generate the audio in the background.
4. Hand you the finished `.mp3`.

## What it is and isn't

Distinct voices reading their turns cleanly, with natural pauses. It produces
clear turn-by-turn narration, not the overlapping, improvised conversation you get
from some commercial audio-overview tools. For a two-host explainer or an
interview read-through, it does the job well.

## Companion project

A GitHub Actions edition shares `core.py` verbatim and runs the same synthesis on
a free Actions runner for anyone with a GitHub account, at the cost of requiring a
fixed `SPEAKER: text` script format instead of free-form input.

## Credits

Voices: [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) via
[kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx), Apache-2.0.
