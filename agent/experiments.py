"""
Experiment log and aggregation.

This is the part that makes it a growth engine rather than a message generator.
Every angle tried on every prospect is recorded with its score, the hard fails
it tripped, and how many revision rounds it needed. Across runs, the aggregate
answers the question the role actually asks:

    which opening angle earns the best message, for which kind of prospect,
    and which angles are reliably a waste of a send?

The honest caveat, stated here because it must also be stated out loud: this
measures DRAFT QUALITY as judged by the critic, not reply rate. Reply rate is
the only metric that finally matters and it requires sending real mail and
waiting. What this gives you is a faster inner loop - you can kill a bad angle
in an afternoon instead of a quarter - and a structure that takes real reply
data the moment you have it (see record_outcome).
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "out" / "experiments" / "log.jsonl"


def record_run(result: dict) -> None:
    """
    Append one row per angle attempt.

    Each row records WHICH GUIDANCE VERSION produced it. Without that, the
    aggregate silently averages attempts written under different instructions
    and reports them as one number - which is what happened on the first run
    after evolve.py shipped: the table mixed 5 pre-evolution attempts with 2
    post-evolution ones and still named a failure mode the new guidance had
    eliminated. An experiment log that cannot distinguish its own conditions
    is not an experiment log.
    """
    from agent.angles import EVOLVED

    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        for a in result["angles"]:
            f.write(
                json.dumps(
                    {
                        "ts": result["generated_at"],
                        "prospect_id": result["prospect_id"],
                        "name": result["name"],
                        "vertical": result["vertical"],
                        "angle": a["angle"],
                        # "original" or "evolved": which instruction set wrote
                        # this draft. Rows without the field predate evolve.py
                        # and are treated as "original".
                        "guidance": "evolved" if a["angle"] in EVOLVED else "original",
                        "final_score": a["final_score"],
                        "shipped": a["shipped"],
                        "rounds_used": a["rounds_used"],
                        "hard_fails_first_round": a["rounds"][0]["hard_fails"],
                        "scores": a["rounds"][-1]["scores"],
                        # Reply outcome is unknown until someone actually sends
                        # it. Null here is honest; a zero would be a measurement.
                        "replied": None,
                    }
                )
                + "\n"
            )


def record_outcome(prospect_id: str, angle: str, replied: bool) -> None:
    """
    Attach a real reply outcome to a logged experiment.

    This is the hook for the only metric that counts. Until it is called with
    real data, aggregate() reports draft quality and says so.
    """
    if not LOG.exists():
        raise SystemExit("No experiment log yet.")
    rows = [json.loads(l) for l in LOG.read_text().splitlines() if l.strip()]
    hit = False
    for r in rows:
        if r["prospect_id"] == prospect_id and r["angle"] == angle:
            r["replied"] = replied
            r["outcome_recorded_at"] = datetime.now(timezone.utc).isoformat()
            hit = True
    if not hit:
        raise SystemExit(f"No logged experiment for {prospect_id}/{angle}")
    LOG.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def aggregate() -> dict:
    if not LOG.exists():
        return {"runs": 0}
    rows = [json.loads(l) for l in LOG.read_text().splitlines() if l.strip()]

    # Group by (angle, guidance version). Averaging across versions hides the
    # very effect the evolution loop exists to produce.
    by_angle = defaultdict(list)
    fails_by_angle = defaultdict(lambda: defaultdict(int))
    for r in rows:
        key = (r["angle"], r.get("guidance", "original"))
        by_angle[key].append(r)
        for hf in r.get("hard_fails_first_round") or []:
            fails_by_angle[key][hf] += 1

    summary = {}
    for angle, rs in by_angle.items():
        scores = [r["final_score"] for r in rs]
        replied = [r["replied"] for r in rs if r["replied"] is not None]
        summary[angle] = {
            "n": len(rs),
            "mean_score": round(sum(scores) / len(scores), 2),
            "ship_rate": round(sum(1 for r in rs if r["shipped"]) / len(rs), 2),
            "mean_rounds": round(sum(r["rounds_used"] for r in rs) / len(rs), 2),
            "common_first_round_failures": dict(
                sorted(fails_by_angle[angle].items(), key=lambda kv: -kv[1])
            ),
            "replies_recorded": len(replied),
            "reply_rate": (
                round(sum(1 for x in replied if x) / len(replied), 3)
                if replied
                else None
            ),
        }

    return {
        "runs": len(rows),
        "angles": dict(sorted(summary.items(), key=lambda kv: (kv[0][0], kv[0][1]))),
        "caveat": (
            "Ranked on critic-judged draft quality, not reply rate. "
            f"{sum(1 for r in rows if r['replied'] is not None)} real outcomes "
            "recorded so far."
        ),
    }


def print_aggregate() -> None:
    a = aggregate()
    if not a.get("runs"):
        print("No experiments logged yet.")
        return
    print(f"\nANGLE PERFORMANCE  ({a['runs']} logged attempts)")
    print("=" * 84)
    print(
        f"{'angle':<18}{'guidance':<11}{'n':>4}{'score':>8}{'ship':>8}"
        f"{'rounds':>8}  top first-round failure"
    )
    print("-" * 84)
    for (angle, version), s in a["angles"].items():
        top = next(iter(s["common_first_round_failures"]), "none")
        print(
            f"{angle:<18}{version:<11}{s['n']:>4}{s['mean_score']:>8.2f}"
            f"{s['ship_rate']:>8.0%}{s['mean_rounds']:>8.2f}  {top}"
        )
    print("-" * 78)
    print(a["caveat"])
