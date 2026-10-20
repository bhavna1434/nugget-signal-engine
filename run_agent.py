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

from agent import card, experiments, loop
from agent.angles import ANGLES
from agent.formats import FORMATS, RENDERED
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
    ap.add_argument(
        "--formats",
        default="email",
        help="comma-separated format keys, or 'all'. "
        f"Available: {', '.join(FORMATS)}",
    )
    ap.add_argument("--sender", default="{sender}", help="name printed on cards")
    ap.add_argument("--url", default="{url}", help="short URL printed on cards")
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
    fmt_keys = list(FORMATS) if args.formats == "all" else args.formats.split(",")
    for f in fmt_keys:
        if f not in FORMATS:
            raise SystemExit(f"Unknown format '{f}'. Available: {', '.join(FORMATS)}")

    targets = [args.prospect] if args.prospect else pick_prospects(args.top)

    usage = Usage()
    llm = LLM(model=args.model, usage=usage) if args.model else LLM(usage=usage)

    print(
        f"Running {len(fmt_keys)} format(s) x {len(angle_keys)} angle(s) "
        f"x {len(targets)} prospect(s) = {len(fmt_keys)*len(angle_keys)*len(targets)} loops"
    )
    print(f"Angles:  {', '.join(ANGLES[a]['name'] for a in angle_keys)}")
    print(f"Formats: {', '.join(FORMATS[f]['name'] for f in fmt_keys)}")

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
        r = loop.run_prospect(llm, pid, angle_keys, formats=fmt_keys)
        experiments.record_run(r)
        results.append(r)

    # Rendered formats become files rather than prose in the terminal.
    cards = []
    for r in results:
        for a in r["angles"]:
            if a.get("format") == "signal_card" and a["final_draft"]:
                c = card.write_card(
                    r["prospect_id"], r["name"], a["final_draft"], args.sender, args.url
                )
                c["prospect"] = r["name"]
                c["shipped"] = a["shipped"]
                cards.append(c)

    out = ROOT / "out" / "agent_output.json"
    out.write_text(json.dumps(results, indent=2))

    print("\n" + "=" * 78)
    print("WINNING MESSAGES")
    print("=" * 78)
    for r in results:
        shipped = [a for a in r["angles"] if a["shipped"]] or r["angles"]
        w = max(shipped, key=lambda a: a["final_score"])
        print(f"\n--- {r['name']}  |  to: {r['target_label']}")
        print(f"    {w['format_name']} / {w['angle_name']}  |  "
              f"score {w['final_score']}  |  {w['rounds_used']} round(s)")
        print(w["final_draft"])

    if cards:
        print("\n" + "=" * 78)
        print("PRINT-READY CARDS")
        print("=" * 78)
        for c in cards:
            miss = f"  MISSING: {', '.join(c['missing'])}" if c["missing"] else ""
            print(f"  {c['prospect']:<16} {c['path']}{miss}")
        print("  Open in a browser and print at 100% scale. A6, 148x105mm.")

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
