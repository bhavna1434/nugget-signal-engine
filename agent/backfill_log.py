"""
One-off: tag existing experiment-log rows with the guidance version that wrote
them.

Rows logged before evolve.py existed carry no `guidance` field, so the
aggregate could not separate pre- and post-evolution attempts and averaged them
together. This assigns each untagged row by comparing its timestamp against the
earliest entry in the evolution changelog.

Safe to run more than once: rows already tagged are left alone.

    python -m agent.backfill_log          # show what it would do
    python -m agent.backfill_log --write  # apply
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "out" / "experiments" / "log.jsonl"
OVERLAY = ROOT / "data" / "angle_evolution.yaml"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    if not LOG.exists():
        raise SystemExit(f"No log at {LOG}")

    rows = [json.loads(l) for l in LOG.read_text().splitlines() if l.strip()]

    # Earliest applied_at per angle: anything logged at or after that moment
    # for that angle was written under evolved guidance.
    applied: dict[str, str] = {}
    if OVERLAY.exists():
        o = yaml.safe_load(OVERLAY.read_text()) or {}
        for e in o.get("changelog", []):
            a, t = e["angle"], e["applied_at"]
            if a not in applied or t < applied[a]:
                applied[a] = t

    if not applied:
        print("No evolution changelog - every row is 'original'.")

    changed = 0
    for r in rows:
        if "guidance" in r:
            continue
        cutoff = applied.get(r["angle"])
        r["guidance"] = "evolved" if cutoff and r["ts"] >= cutoff else "original"
        changed += 1

    counts: dict[tuple, int] = {}
    for r in rows:
        k = (r["angle"], r["guidance"])
        counts[k] = counts.get(k, 0) + 1

    print(f"{len(rows)} rows, {changed} newly tagged\n")
    for (angle, v), n in sorted(counts.items()):
        print(f"  {angle:<18}{v:<11}{n}")

    if args.write:
        LOG.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        print(f"\nWritten -> {LOG}")
    else:
        print("\nDry run. Re-run with --write to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
