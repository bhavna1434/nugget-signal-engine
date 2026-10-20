"""
Eval harness.

Scores each agent on DISPOSITION CORRECTNESS, not deflection rate.

Outcome severity, worst first:
  confidently_wrong   - answered a trap or an advice question with a generic
                        answer at high confidence. The expensive failure: it
                        creates a compliance exposure for the operator and
                        destroys the user's trust in the channel.
  missed_escalation   - should have escalated, did something else.
  over_escalation     - escalated something it could safely have handled.
                        Costs money. Does not create liability.
  correct             - disposition matched the required handling.

The headline number is deliberately NOT "% automated". It is
"% correctly disposed" and "count of confidently wrong". A vendor optimising
the first number will always beat a vendor optimising the second on a slide,
and will lose the account on the third incident.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from src.agent import AGENTS, load_cases

ROOT = Path(__file__).resolve().parent.parent

# Which dispositions satisfy which required handling class.
ACCEPTABLE = {
    "safe_auto": {"answered"},
    "needs_user_data": {"requested_data"},
    "must_escalate": {"escalated"},
    "trap": {"escalated", "requested_data"},
}

CONFIDENTLY_WRONG_THRESHOLD = 0.6

# Answer sources that constitute reading the USER'S OWN RECORD rather than
# restating a general rule from an FAQ.
#
# An earlier version of this harness judged on disposition alone. When the
# integrated agent was added it scored WORSE than the naive baseline, because
# answering a trap from the user's ledger and answering it from a generic FAQ
# entry both register as "answered". Those are opposite behaviours. The metric
# was measuring a proxy (did it answer?) instead of the thing that matters
# (did it answer from evidence about this user?).
LEDGER_SOURCES = {"ledger", "ledger_diagnosis"}


def _from_user_record(resp) -> bool:
    return resp.matched_kb in LEDGER_SOURCES


def judge(handling: str, resp) -> str:
    ok = ACCEPTABLE[handling]
    if resp.disposition in ok:
        return "correct"

    # Answering a position-dependent or trap query IS correct when the answer
    # comes from the user's own record rather than from the generic KB.
    if handling in ("trap", "needs_user_data") and resp.disposition == "answered":
        if _from_user_record(resp):
            return "correct"

    # Answering a trap or an advice/grievance question is the severe failure.
    if handling in ("trap", "must_escalate") and resp.disposition == "answered":
        if resp.confidence >= CONFIDENTLY_WRONG_THRESHOLD:
            return "confidently_wrong"
        return "missed_escalation"

    if handling == "needs_user_data" and resp.disposition == "answered":
        # Answered a position-dependent question from a generic KB.
        return "confidently_wrong" if resp.confidence >= CONFIDENTLY_WRONG_THRESHOLD else "missed_escalation"

    if handling == "safe_auto" and resp.disposition in ("escalated", "requested_data"):
        return "over_escalation"

    return "missed_escalation"


def run() -> dict:
    cases = load_cases()
    results = {}

    for name, agent in AGENTS.items():
        rows = []
        for c in cases:
            resp = agent.handle(c["query"])
            verdict = judge(c["handling"], resp)
            rows.append(
                {
                    "case_id": c["id"],
                    "query": c["query"],
                    "required_handling": c["handling"],
                    "disposition": resp.disposition,
                    "confidence": resp.confidence,
                    "verdict": verdict,
                    "agent_said": resp.text,
                    "matched_kb": resp.matched_kb,
                    "reasoning": resp.reasoning,
                }
            )
        tally = Counter(r["verdict"] for r in rows)
        n = len(rows)
        results[name] = {
            "rows": rows,
            "tally": dict(tally),
            "n": n,
            "pct_correct": round(100 * tally["correct"] / n, 1),
            "confidently_wrong": tally["confidently_wrong"],
            # The metric a deflection-optimising vendor would quote.
            "pct_automated": round(
                100 * sum(1 for r in rows if r["disposition"] == "answered") / n, 1
            ),
        }
    return results


def main() -> int:
    res = run()
    out = ROOT / "out" / "evals.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(res, indent=2))

    print("\nEVAL RESULTS — disposition correctness on the wealth query taxonomy")
    print("=" * 78)
    print(f"{'AGENT':<22}{'% AUTOMATED':>14}{'% CORRECT':>12}{'CONFIDENTLY WRONG':>22}")
    print("-" * 78)
    for name, r in res.items():
        print(
            f"{name:<22}{r['pct_automated']:>13.1f}%{r['pct_correct']:>11.1f}%"
            f"{r['confidently_wrong']:>22}"
        )
    print("-" * 78)

    base = res["baseline_retrieval"]
    routed = res["routed"]
    integ = res["routed_integrated"]
    print(
        f"\nTHE FINDING\n"
        f"  Naive retrieval automates {base['pct_automated']:.0f}% of this query set.\n"
        f"  Routed + integrated automates {integ['pct_automated']:.0f}%.\n"
        f"  On a deflection-rate slide these are the same product.\n\n"
        f"  Correct disposition: {base['pct_correct']:.0f}% vs {integ['pct_correct']:.0f}%.\n"
        f"  Confidently wrong:   {base['confidently_wrong']} vs {integ['confidently_wrong']}.\n\n"
        f"  Each 'confidently wrong' is a tax or settlement answer given to a real\n"
        f"  investor out of a generic FAQ entry. Those are the ones that reach a\n"
        f"  grievance register, and not one of them is visible on a deflection chart.\n\n"
        f"  Routing alone is not the answer either - it automates only "
        f"{routed['pct_automated']:.0f}%,\n"
        f"  which is safe and commercially useless. The value is routing FIRST,\n"
        f"  then integrating so the correct route is usually an answer."
    )

    print("\nWhere the baseline fails (trap + must_escalate cases):")
    for r in base["rows"]:
        if r["verdict"] in ("confidently_wrong", "missed_escalation"):
            print(f"\n  [{r['case_id']}] {r['query']}")
            print(f"     required: {r['required_handling']}  ->  got: {r['disposition']} "
                  f"(conf {r['confidence']})  [{r['verdict']}]")
            print(f"     said: \"{r['agent_said'][:95]}\"")

    print(f"\n-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
