"""
Self-improvement loop: the engine rewrites its own angle instructions.

WHAT THIS IS
------------
After every run, each angle carries a record of how its drafts failed review.
This reads that record, finds the failure mode that is DOMINANT for a given
angle, and asks the model to rewrite that angle's guidance so the next draft
pre-empts it. The rewritten guidance is stored as an overlay and applied on the
next run.

This closes the loop that was previously closed by hand. After the first live
run the critic rejected 10 of 12 drafts and nearly every rejection said the
same thing - the draft gave the reader nothing. A human read that, inferred the
missing rule, and edited angles.py. That inference is mechanical: find the
failure that recurs for one angle and not others, and write a rule against it.

WHY IT PROPOSES RATHER THAN APPLIES
------------------------------------
Prompts that rewrite themselves unattended drift. A small degradation compounds
over runs and there is no way to see when it started, because the thing that
would tell you is the thing that changed. So:

  - evolve.py writes a PROPOSAL with the evidence that motivated it
  - a human reads it and runs --apply
  - every applied change is versioned with its evidence and timestamp
  - angles.py is never modified; evolution lives in data/angle_evolution.yaml,
    so rollback is deleting one file and nothing is ever lost

A system that changes its own instructions without a record is not improving,
it is wandering.

GUARDS
------
MIN_ATTEMPTS      an angle needs real history before its failures mean anything
MIN_FAILURE_RATE  the failure must be dominant, not merely present
                  (3 of 5 is a pattern; 1 of 5 is noise)

Usage:
    python -m agent.evolve                 # analyse and propose
    python -m agent.evolve --apply         # apply pending proposals
    python -m agent.evolve --history       # show what changed and why
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "out" / "experiments" / "log.jsonl"
OVERLAY = ROOT / "data" / "angle_evolution.yaml"
PROPOSALS = ROOT / "out" / "evolution_proposals.json"

MIN_ATTEMPTS = 4
MIN_FAILURE_RATE = 0.5

FAILURE_MEANING = {
    "unsupported_claim": "stated a specific fact about the company that was not in the brief",
    "generic_opening": "opened with a line that would work for any company in the sector",
    "asks_for_meeting": "requested a call or meeting in a first touch",
    "over_length": "exceeded the word limit",
    "manufactured_urgency": "invented time pressure or scarcity",
    "caveat_stripped": "presented a figure as more conclusive than the data supports",
    "derived_figure": "restated a number in a form the brief does not use, e.g. "
    "converting a percentage into a count",
    "nothing_offered": "gave the recipient nothing they keep whether or not they reply",
}

SYSTEM = """You tune the instructions given to a cold-outreach writer.

You are given one angle's current guidance and hard evidence about how its \
drafts keep failing review. Rewrite the guidance so the next draft pre-empts \
that specific failure.

Rules:
- Keep the angle's STRATEGY intact. You are fixing how it is executed, not \
replacing it with a different angle. If the angle leads with a customer quote, \
it still leads with a customer quote afterwards.
- Address the named failure mode directly and concretely. A writer reading your \
guidance should know exactly what not to do and what to do instead.
- Keep it to 2-4 sentences. This is operational guidance, not an essay.
- Do not add generic advice about good writing. Fix the named failure."""

TEMPLATE = """ANGLE: {name}
STRATEGY (do not change this): {thesis}

CURRENT GUIDANCE:
{guidance}

EVIDENCE FROM {n} LOGGED ATTEMPTS:
This angle tripped the hard fail "{failure}" on {count} of {n} first drafts \
({rate:.0%}).
That failure means: {meaning}

Comparison: {comparison}

Rewrite the guidance so this failure stops happening. Return ONLY the new \
guidance text, no preamble, no quotes around it."""


def load_log() -> list[dict]:
    if not LOG.exists():
        raise SystemExit(
            f"No experiment log at {LOG}.\nRun the agent first: python run_agent.py --top 2"
        )
    return [json.loads(l) for l in LOG.read_text().splitlines() if l.strip()]


def analyse(rows: list[dict]) -> dict:
    """Per-angle failure profile from the logged attempts."""
    by_angle = defaultdict(list)
    fails = defaultdict(lambda: defaultdict(int))
    for r in rows:
        by_angle[r["angle"]].append(r)
        for hf in r.get("hard_fails_first_round") or []:
            fails[r["angle"]][hf] += 1

    out = {}
    for angle, rs in by_angle.items():
        n = len(rs)
        ranked = sorted(fails[angle].items(), key=lambda kv: -kv[1])
        scores = [r["final_score"] for r in rs]
        out[angle] = {
            "n": n,
            "mean_score": round(sum(scores) / n, 2),
            "ship_rate": round(sum(1 for r in rs if r["shipped"]) / n, 2),
            "failures": dict(ranked),
            "dominant": ranked[0] if ranked else None,
        }
    return out


def _comparison(angle: str, failure: str, profile: dict) -> str:
    """How other angles fare on the same failure - evidence it is angle-specific."""
    others = []
    for a, p in profile.items():
        if a == angle:
            continue
        c = p["failures"].get(failure, 0)
        others.append(f"{a} tripped it {c} of {p['n']}")
    if not others:
        return "no other angle has enough history to compare against."
    return (
        "; ".join(others)
        + ". A failure that is heavy for this angle and light for others is a "
        "flaw in this angle's instructions, not a general writing problem."
    )


def propose(llm, profile: dict, angles: dict) -> list[dict]:
    proposals = []
    for angle, p in profile.items():
        if p["n"] < MIN_ATTEMPTS:
            proposals.append(
                {"angle": angle, "skipped": f"only {p['n']} attempts (min {MIN_ATTEMPTS})"}
            )
            continue
        if not p["dominant"]:
            proposals.append({"angle": angle, "skipped": "no hard fails recorded"})
            continue

        failure, count = p["dominant"]
        rate = count / p["n"]
        if rate < MIN_FAILURE_RATE:
            proposals.append(
                {
                    "angle": angle,
                    "skipped": f"top failure '{failure}' at {rate:.0%}, "
                    f"below {MIN_FAILURE_RATE:.0%} - not a pattern",
                }
            )
            continue

        current = angles[angle]["guidance"]
        user = TEMPLATE.format(
            name=angles[angle]["name"],
            thesis=angles[angle]["thesis"],
            guidance=current,
            n=p["n"],
            failure=failure,
            count=count,
            rate=rate,
            meaning=FAILURE_MEANING.get(failure, failure),
            comparison=_comparison(angle, failure, profile),
        )
        new = llm.complete(f"evolve:{angle}", SYSTEM, user, max_tokens=4000).strip()

        proposals.append(
            {
                "angle": angle,
                "evidence": {
                    "attempts": p["n"],
                    "failure": failure,
                    "count": count,
                    "rate": round(rate, 2),
                    "mean_score_before": p["mean_score"],
                    "ship_rate_before": p["ship_rate"],
                },
                "current_guidance": current,
                "proposed_guidance": new,
                "proposed_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    return proposals


def apply(proposals: list[dict]) -> int:
    """Write accepted proposals into the overlay, preserving full history."""
    overlay = yaml.safe_load(OVERLAY.read_text()) if OVERLAY.exists() else {}
    overlay.setdefault("angles", {})
    overlay.setdefault("changelog", [])

    applied = 0
    for p in proposals:
        if p.get("skipped"):
            continue
        angle = p["angle"]
        overlay["angles"][angle] = {"guidance": p["proposed_guidance"]}
        overlay["changelog"].append(
            {
                "angle": angle,
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "because": (
                    f"tripped '{p['evidence']['failure']}' on "
                    f"{p['evidence']['count']} of {p['evidence']['attempts']} "
                    f"first drafts ({p['evidence']['rate']:.0%})"
                ),
                "mean_score_before": p["evidence"]["mean_score_before"],
                "previous_guidance": p["current_guidance"],
            }
        )
        applied += 1

    OVERLAY.write_text(
        "# Evolved angle guidance - WRITTEN BY agent/evolve.py, NOT BY HAND.\n"
        "#\n"
        "# angles.py holds the original guidance and is never modified. This file\n"
        "# overlays it. Delete it to revert every angle to its original wording.\n"
        "#\n"
        "# Every entry in the changelog carries the evidence that motivated it and\n"
        "# the guidance it replaced, so any change can be read, judged and undone.\n\n"
        + yaml.safe_dump(overlay, sort_keys=False, width=88, allow_unicode=True)
    )
    return applied


def show_history() -> None:
    if not OVERLAY.exists():
        print("No evolution history - angles are all original.")
        return
    o = yaml.safe_load(OVERLAY.read_text())
    log = o.get("changelog", [])
    print(f"\nEVOLUTION HISTORY ({len(log)} applied changes)")
    print("=" * 78)
    for e in log:
        print(f"\n{e['applied_at'][:16]}  {e['angle']}")
        print(f"  because: {e['because']}")
        print(f"  mean score at the time: {e['mean_score_before']}")
        print(f"  replaced: \"{e['previous_guidance'][:110]}...\"")
    print()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="apply the pending proposals")
    ap.add_argument("--history", action="store_true", help="show what has changed and why")
    args = ap.parse_args()

    if args.history:
        show_history()
        return 0

    if args.apply:
        if not PROPOSALS.exists():
            raise SystemExit("No proposals. Run `python -m agent.evolve` first.")
        proposals = json.loads(PROPOSALS.read_text())["proposals"]
        n = apply(proposals)
        print(f"Applied {n} change(s) -> {OVERLAY}")
        print("The next agent run uses the evolved guidance.")
        print("Revert everything: rm data/angle_evolution.yaml")
        return 0

    from agent.angles import ANGLES
    from agent.llm import LLM, Usage

    rows = load_log()
    profile = analyse(rows)

    print(f"\nFAILURE PROFILE  ({len(rows)} logged attempts)")
    print("=" * 78)
    for angle, p in profile.items():
        top = f"{p['dominant'][0]} x{p['dominant'][1]}" if p["dominant"] else "none"
        print(
            f"{angle:<18} n={p['n']:<3} score={p['mean_score']:<6} "
            f"ship={p['ship_rate']:.0%}  dominant failure: {top}"
        )

    usage = Usage()
    proposals = propose(LLM(usage=usage), profile, ANGLES)

    PROPOSALS.parent.mkdir(parents=True, exist_ok=True)
    PROPOSALS.write_text(
        json.dumps(
            {"generated_at": datetime.now(timezone.utc).isoformat(), "proposals": proposals},
            indent=2,
        )
    )

    print("\n" + "=" * 78)
    print("PROPOSED CHANGES")
    print("=" * 78)
    for p in proposals:
        if p.get("skipped"):
            print(f"\n{p['angle']}: no change - {p['skipped']}")
            continue
        e = p["evidence"]
        print(f"\n{p['angle']}  (tripped '{e['failure']}' {e['count']}/{e['attempts']})")
        print(f"\n  BEFORE: {p['current_guidance']}")
        print(f"\n  AFTER:  {p['proposed_guidance']}")

    print("\n" + "=" * 78)
    print(usage.summary())
    print(f"-> {PROPOSALS}")
    print("\nReview the above, then: python -m agent.evolve --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
