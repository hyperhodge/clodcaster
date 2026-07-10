---
name: clodcaster
description: "Turn a script into podcast-style audio with distinct neural voices. Use whenever the user wants to convert dialogue, a conversation, an interview, notes, or any script into spoken audio / an audio file / a podcast episode. Accepts a raw script in ANY format — the user does not need to structure it. Triggers: 'make this a podcast', 'turn this into audio', 'read this as a conversation', 'generate an episode', 'text to speech for two hosts', mentions of podcast/audio/voices/narration from a script. Produces an mp3 with British hosts by default. Runs fully offline on CPU, no API keys."
license: Apache-2.0
---

# Podcast audio from a script

Converts a script into a stitched multi-voice audio episode using Kokoro (fp16,
ONNX) — neural voices, running on CPU in this environment, no API keys, no
external services. Two British hosts by default (female + male), clean
turn-taking between them.

Output is distinct voices reading their turns cleanly, with pauses between them.
If a user expects overlapping, improvised, conversational banter (as in some
commercial audio-overview products), tell them plainly that this produces clear
turn-by-turn narration rather than spontaneous conversation.

## Pipeline

1. Normalise the user's raw script into tagged turns. This is what makes any
   input format work.
2. Show the user the tagged interpretation and confirm before synthesising.
3. Run synthesis in the background; poll until done.
4. Present the finished mp3.

## Step 1 — Normalise to turns

The user brings a script in whatever shape they have: a rough dialogue, an
interview transcript, a monologue, bullet notes, an outline. Convert it into a
JSON list of turns:

```json
[
  {"speaker": "ALEX", "text": "First line spoken by Alex."},
  {"speaker": "SAM",  "text": "Sam's reply."}
]
```

Rules for normalisation:
- Infer speaker labels and turn boundaries from the text. Keep labels consistent.
- Default is a two-host conversation. If the raw script is a monologue, use a
  single speaker (one voice is fine). If you detect **more than two** speakers,
  keep them — each distinct speaker gets its own voice — but tell the user, since
  only two have curated British defaults and any extras fall back to other voices.
- Strip anything non-spoken: stage directions, `[music]`, timestamps, headings,
  speaker bios. Only spoken words get synthesised.
- Expand awkward-for-speech tokens into words where obvious (e.g. "£5m" ->
  "five million pounds", "AI" is fine spoken as-is). Don't rewrite the user's
  content or editorialise — just make it speakable.
- To override a voice for a speaker, add `"voice"` to any of their turns using a
  friendly name (emma, george, alice, lily, daniel, lewis) or a raw Kokoro ID
  (e.g. bf_emma, bm_george). Otherwise speakers map in first-seen order to the
  default British pair.

Write the turns to a JSON file, e.g. `/tmp/turns.json`.

## Step 2 — Confirm before synthesising

Show the user the normalised turns (speaker -> a line or two each) and the voice
each speaker will get. Ask them to confirm or adjust. This matters: synthesis is
CPU-bound (~0.7s of compute per 1s of audio on one core), so a 20-minute episode
is real minutes of work. Confirming first avoids wasting it on a
misinterpretation. Skip this only if the user explicitly says "just do it".

## Step 3 — Synthesise in the background

Do NOT run synthesis as one blocking command — a long episode can exceed the
execution time limit. Use the background runner and poll:

```bash
# Start (returns immediately with a job_dir). Output as .mp3.
python scripts/run.py start /tmp/turns.json /mnt/user-data/outputs/episode.mp3
```

That prints `{"job_dir": "...", ...}`. Then, in **separate** commands spaced out,
check status until done:

```bash
python scripts/run.py status <job_dir>
```

Status returns live progress: `turns_done`, `turns_total`, `audio_seconds`,
`elapsed_seconds`, and `state`. When `state` is `done`, the result includes the
final `out_path`, `duration_seconds`, and `voice_mapping`. If `state` is `error`,
a `log_tail` explains what failed.

For short scripts (a handful of turns) you may instead block and wait:

```bash
python scripts/run.py wait <job_dir> 10
```

First run in a session downloads the voice model (~170MB) + voices (~27MB) from a
GitHub release into `~/.cache/podcast-tts`, then caches them. Tell the user the
first episode is slower for this reason; later ones in the same session skip it.

## Step 4 — Present

Once done, present the mp3 from `/mnt/user-data/outputs/` with the
`present_files` tool so the user can download it. Mention duration and which voice
each host got.

## Voices

British defaults: `emma` (bf_emma, female), `george` (bm_george, male). Other
British options: `alice`, `lily` (female), `daniel`, `lewis` (male). Any Kokoro
voice ID also works if the user wants American or other accents (e.g. af_heart,
am_michael) — pass it as the `voice` on that speaker's turns and it overrides.

## Notes / limits

- Output is mp3 (via ffmpeg) when the path ends `.mp3`, otherwise wav.
- Synthesis runs one turn at a time, so longer scripts take proportionally
  longer. There is no fixed episode-length cap; the background runner is what
  keeps long jobs within the per-step time limit.
- The environment's network allowlist reaches the GitHub release host used for
  weights. If that ever changes, weight download is the thing that breaks first.
- Dependencies: `kokoro-onnx`, `soundfile` (pip install with
  `--break-system-packages`), and `ffmpeg` (already present).

## Companion project

`scripts/core.py` is shared verbatim with a GitHub Actions edition of this tool,
which runs the same synthesis on a free Actions runner for anyone with a GitHub
account (no Claude subscription needed) but requires a fixed `SPEAKER: text`
script format instead of the free-form normalisation this skill does. Use this
skill for any-format input inside Claude; use the Actions edition for broad,
non-Claude distribution.
