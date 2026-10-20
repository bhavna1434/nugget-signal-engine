"""
AI-powered outreach engine — entry point.

    export ANTHROPIC_API_KEY=sk-ant-...
    python run_agent.py --top 3
    python run_agent.py --prospect smallcase --angles evidence_audit,single_quote
    python run_agent.py --report

Runs the full loop: research brief from measured data -> draft in each angle ->
critic review -> revise until it passes or the round budget is spent -> log the
experiment -> write the winners.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent import experiments, loop
from agent.angles import ANGLES
from agent.llm import LLM, Usage

ROOT = Path(__file__).resolve().parent


def pick_prospects(n: int) -> list[str]:
    p = ROOT / "out" / "pipeline.json"
    if not p.exists():
        raise SystemExit(
            "Run the signal pipeline first:\n"
            "  python -m src.collect_playstore && python -m src.classify "
            "&& python -m src.score && python -m src.run_evals"
        )
    rows = json.loads(p.read_text())["pipeline"]
    return [r["prospect_id"] for r in rows if r["contactable"]][:n]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=3, help="run the top N contactable prospects")
    ap.add_argument("--prospect", help="run one prospect by id")
    ap.add_argument(
        "--angles",
        default="evidence_audit,single_quote,question_first",
        help="comma-separated angle keys, or 'all'",
    )
    ap.add_argument("--report", action="store_true", help="print the experiment aggregate and exit")
    ap.add_argument("--model", default=None)
    args = ap.parse_args()

    if args.report:
        experiments.print_aggregate()
        return 0

    angle_keys = list(ANGLES) if args.angles == "all" else args.angles.split(",")
    for a in angle_keys:
        if a not in ANGLES:
            raise SystemExit(f"Unknown angle '{a}'. Available: {', '.join(ANGLES)}")

    targets = [args.prospect] if args.prospect else pick_prospects(args.top)

    usage = Usage()
    llm = LLM(model=args.model, usage=usage) if args.model else LLM(usage=usage)

    print(f"Running {len(angle_keys)} angles x {len(targets)} prospects")
    print(f"Angles: {', '.join(ANGLES[a]['name'] for a in angle_keys)}")

    # Say which version of the instructions produced this run. Without it, two
    # runs with different scores are not comparable and you cannot tell whether
    # a change helped.
    from agent.angles import EVOLVED

    evolved_here = [a for a in angle_keys if a in EVOLVED]
    if evolved_here:
        print(
            f"Guidance: EVOLVED for {', '.join(evolved_here)} "
            f"(see python -m agent.evolve --history)"
        )
    else:
        print("Guidance: original")

    results = []
    for pid in targets:
        r = loop.run_prospect(llm, pid, angle_keys)
        experiments.record_run(r)
        results.append(r)

    out = ROOT / "out" / "agent_output.json"
    out.write_text(json.dumps(results, indent=2))

    print("\n" + "=" * 78)
    print("WINNING MESSAGES")
    print("=" * 78)
    for r in results:
        w = next(a for a in r["angles"] if a["angle"] == r["winning_angle"])
        print(f"\n--- {r['name']}  |  angle: {w['angle_name']}  |  "
              f"score {w['final_score']}  |  {w['rounds_used']} round(s)")
        print(w["final_draft"])

    total_rounds = sum(a["rounds_used"] for r in results for a in r["angles"])
    rejected = sum(
        1 for r in results for a in r["angles"] for rd in a["rounds"] if not rd["passed"]
    )
    print("\n" + "=" * 78)
    print(f"{total_rounds} drafts written, {rejected} rejected by review before shipping")
    print(usage.summary())
    print(f"-> {out}")
    experiments.print_aggregate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
