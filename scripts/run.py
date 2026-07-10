"""
Background runner for the podcast skill.

Long episodes take minutes of CPU on the single-core sandbox. Running that as
one blocking command risks the per-execution wall-clock limit. So synthesis is
launched detached; the caller polls a progress file instead of waiting.

Usage:
  python run.py start <turns.json> <out.wav>   -> prints job dir, returns immediately
  python run.py status <job_dir>               -> prints current progress JSON
  python run.py wait <job_dir> [poll_seconds]  -> polls until done, prints result

Typical skill flow: `start`, then `status` in a fresh command every so often
until state == "done", then present the finished file.
"""

import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.join(HERE, "core.py")


def start(turns_path, out_path):
    job_dir = os.path.join("/tmp", f"podcast_job_{int(time.time())}")
    os.makedirs(job_dir, exist_ok=True)
    progress = os.path.join(job_dir, "progress.json")
    result = os.path.join(job_dir, "result.json")
    log = os.path.join(job_dir, "run.log")

    with open(progress, "w") as f:
        json.dump({"state": "starting", "turns_done": 0, "turns_total": 0}, f)

    # Detached child: synthesise, then write result.json on completion.
    child = (
        f"import json,sys; sys.path.insert(0,{HERE!r}); import core; "
        f"r=core.synthesise(json.load(open({turns_path!r})), {out_path!r}, "
        f"progress_path={progress!r}); json.dump(r, open({result!r},'w'))"
    )
    with open(log, "w") as lf:
        subprocess.Popen(
            [sys.executable, "-c", child],
            stdout=lf, stderr=lf, start_new_session=True,
        )
    print(json.dumps({"job_dir": job_dir, "progress": progress, "result": result}))
    return job_dir


def status(job_dir):
    progress = os.path.join(job_dir, "progress.json")
    result = os.path.join(job_dir, "result.json")
    log = os.path.join(job_dir, "run.log")
    if os.path.exists(result):
        with open(result) as f:
            print(json.dumps({"state": "done", **json.load(f)}))
        return "done"
    if os.path.exists(progress):
        with open(progress) as f:
            p = json.load(f)
        # surface a crash if the child died mid-run
        if p.get("state") != "done" and os.path.exists(log):
            tail = open(log).read()[-500:]
            if "Traceback" in tail:
                print(json.dumps({"state": "error", "log_tail": tail}))
                return "error"
        print(json.dumps(p))
        return p.get("state", "running")
    print(json.dumps({"state": "unknown"}))
    return "unknown"


def wait(job_dir, poll=10):
    while True:
        st = status(job_dir)
        if st in ("done", "error", "unknown"):
            return
        time.sleep(poll)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "start":
        start(sys.argv[2], sys.argv[3])
    elif cmd == "status":
        status(sys.argv[2])
    elif cmd == "wait":
        wait(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 10)
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)
