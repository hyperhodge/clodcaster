# ClodCaster — Technical Specification

## Overview

This document specifies a tool that converts a written script into podcast-style
audio: two or more distinct speaking voices, with natural pauses between turns.
The design goal is that it should be free to run and free to distribute, needing
no paid services, no API keys, and no server for the author to maintain. The
output is a single downloadable audio file (mp3).

The tool ships in two editions that share one synthesis engine, described below.

## A note on terminology

This document uses a few terms from speech and machine-learning work. They are
explained here in plain language.

- **Text-to-speech (TTS):** software that reads written text aloud in a synthetic
  voice.
- **Neural voice / neural-quality speech:** speech produced by a neural network
  (a machine-learning model trained on many hours of recorded human speech). The
  practical point is that it sounds far closer to a real person than the older,
  robotic "screen reader" voices built into operating systems. "Neural-quality"
  here simply means "sounds reasonably human", as opposed to obviously mechanical.
- **Model / weights:** the trained network is called a *model*; the large data
  file holding what it learned is its *weights*. Running the tool requires
  downloading this weights file once.
- **ONNX:** a standard file format for machine-learning models that lets them run
  efficiently on an ordinary computer's processor (CPU) without special hardware.
- **Quantisation (fp32 / fp16 / int8):** a way of shrinking a model by storing its
  numbers at lower precision. *fp32* is full precision (largest, most exact),
  *fp16* is half precision (about half the size), and *int8* is compressed to
  whole numbers (smallest). Lower precision usually means smaller and faster, but
  the effect on speed depends heavily on the specific processor, as the
  measurements below show.
- **Real-time factor (RTF):** how long synthesis takes relative to the length of
  audio produced. RTF 0.7 means seven seconds of computing per ten seconds of
  finished audio. Lower is faster; below 1.0 means faster than real time.
- **CPU / core:** the processor that does the work. A *core* is one independent
  worker inside it. More cores allow more tasks to run at once; a single core must
  do everything in sequence.

## Requirements

The tool must be free to run and free to share, with nothing for the author to
host or pay for. It must not require the user to supply API keys or paid tokens.
It must produce multiple distinct voices, each keeping a consistent identity
across an episode, with natural pauses between turns. It should support episodes
of useful length (up to roughly thirty minutes). It should be portable enough that
others can adopt it without having to trust the author with credentials or data.

## Architecture: two editions, one engine

The speech-synthesis and audio-stitching code is the core asset and is identical
across both editions. Only the surrounding wrapper differs.

| | Skill edition | Automation edition |
|---|---|---|
| Input | A script in any format, interpreted by an AI assistant | A fixed `SPEAKER: text` line format |
| Where it runs | Inside an AI assistant's execution sandbox (CPU) | On a free continuous-integration runner (e.g. GitHub Actions) |
| Audience | Users of that AI assistant | Anyone with an account on the CI platform |
| Meaning of "free" | Free at the point of use to subscribers | Free for public repositories |
| Weight download | Re-fetched each session | Cached between runs |

The two editions answer two different definitions of "free". The skill edition is
the low-friction experience for people already inside the AI assistant, and it can
accept a script in any shape because the assistant normalises it. The automation
edition works for anyone with a CI account and, because CI runners typically have
several cores, can run faster (see Performance).

## Chosen speech engine

The tool uses an open-source neural TTS model (Kokoro) in ONNX format, chosen
because it produces natural-sounding speech, runs on an ordinary CPU with no
special hardware, is small enough to download quickly, and is permissively
licensed. It provides a range of voices including several British male and female
options, so a two-host show can have distinct, consistent voices with no
voice-cloning step required.

Selecting a model for a constrained sandbox is an empirical exercise, not a matter
of received wisdom. Two environment facts, established by testing rather than
assumption, drove the choice:

- The sandbox's network is restricted to an allow-list of domains. The most common
  model-hosting site was blocked, which ruled out otherwise-strong models whose
  weights live only there. A public code-hosting platform's release downloads were
  reachable, which made models distributed that way viable.
- The sandbox provides a single CPU core (verified via processor count, CPU
  affinity, and resource quota). This removes parallelism as an option: with one
  core, work happens strictly in sequence.

## Precision choice (fp16)

Three precision variants of the model were benchmarked on identical text:

| Variant | Real-time factor (lower = faster) | Download size |
|---|---|---|
| fp32 (full precision) | 1.04 | 311 MB |
| **fp16 (half precision) — chosen** | **0.69–0.75** | **170 MB** |
| int8 (compressed) | 1.79 | 89 MB |

fp16 was the best all-round choice: the fastest to synthesise *and* about half the
download of full precision. The int8 variant, despite being the smallest, was the
**slowest** on this processor, because the specialised instructions its
compression relies on were not well supported and the software fell back to slow
code paths. This illustrates why smaller does not automatically mean faster, and
why measuring on the target hardware matters.

## Performance and its consequences

At the chosen settings, real-time factor is roughly 0.7, meaning a ten-minute
episode takes around seven minutes of computing on the single-core sandbox. This
has two consequences.

First, on the skill edition, synthesis must run in the background with the caller
polling for progress, rather than as one long blocking command, so that a lengthy
episode does not exceed the sandbox's per-step time limit.

Second, raw speed is fundamentally bounded by the single core. Measured levers
that help within that limit:

- **Speaking rate.** Raising the delivery to a mild 1.2x (a normal brisk podcast
  pace) cut compute by roughly 15% with no meaningful loss of naturalness.
- **Batching text within a turn.** Combining a turn's sentences into one synthesis
  call avoided about 170 ms of per-call overhead each time, lowering RTF from
  ~0.69 to ~0.61 in testing.
- **Perceived speed.** Producing audio progressively, so the listener can begin
  playback before the whole episode has rendered, improves the experience more
  than shaving seconds off the total.

The largest speed gain is architectural: the automation edition runs on multi-core
CI runners, where turns can be synthesised in parallel — something the single-core
sandbox cannot do. Where speed is the priority, that edition is the answer.

Approaches that did **not** help, and should not be pursued: the int8 model (slower
here, as shown); further runtime tuning (graph optimisation is already at maximum
and threads are auto-configured); and swapping to a smaller model (quality cost for
little gain).

## Design decisions

- **Input format.** The skill edition accepts a script in any format and has the AI
  assistant convert it into tagged turns — the step generic wrappers cannot do. The
  automation edition, having no AI assistant in the loop, uses a documented
  `SPEAKER: text` format with a small parser.
- **Review before synthesis.** The skill edition shows the user its interpretation
  of the script and the voice each speaker will receive, and confirms before
  committing minutes of compute. During development this review discipline, backed
  by automated tests, caught a real bug in voice assignment.
- **Voices.** A British female and British male pairing by default, overridable per
  speaker to any available voice.
- **Music and intro/outro.** Out of scope for the first version; voices only.
- **Output.** mp3 (roughly a sixth the size of uncompressed audio).

## Scope: what it is and is not

The tool produces distinct voices reading their turns cleanly, with natural pauses.
It does **not** produce the overlapping, laughing, improvised co-host banter
associated with some commercial "audio overview" products. That style requires
substantially heavier models purpose-built for multi-speaker conversation, which do
not fit a CPU-only sandbox. For a two-host explainer, an interview read-through, or
narrated dialogue, the tool is well suited; marketing should claim clean
turn-taking, not spontaneous conversational chemistry.

## Known risks

- **Sandbox coupling (skill edition).** The network allow-list, time limits, and
  package-installation behaviour of the sandbox are controlled by its operator and
  can change. A skill that silently breaks when the allow-list shifts is a poor
  distribution story. The automation edition, whose compute layer is controlled by
  a different party, is a partial hedge.
- **Per-session weight download (skill edition).** The sandbox resets between
  sessions, so each session re-downloads the model (around 200 MB). fp16 nearly
  halves this versus full precision, but it remains the most fragile link. CI
  runners cache the weights between runs, so the automation edition avoids it.
- **Single upstream host.** Both editions download the model from one code-hosting
  release. If that asset moves, downloads break. Mirroring the weights is cheap
  insurance if the tool sees real use.

## Roadmap (deferred)

- **In-browser edition.** The model has a JavaScript port that can run entirely in
  the user's web browser, served from a static page. Hosting cost would then be nil
  permanently, with synthesis on the user's own device. Browser synthesis is slower
  for long episodes, so this is a later addition rather than a first version.
- **Heavier conversational model** on the automation or browser editions, where
  more compute is available, to lift quality above stitched single-speaker turns.

## Explicitly excluded

A popular approach that rides a free endpoint from a major vendor's browser was
considered and rejected: it offers good voices at almost no compute cost, but the
endpoint is undocumented, its terms of use are ambiguous, and it is blocked by the
sandbox's allow-list in any case.
