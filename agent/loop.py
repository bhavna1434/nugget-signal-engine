"""
The agent loop: draft -> critique -> revise, per angle, per prospect.

Every round is recorded, including the rejected ones. The rejections are the
most interesting output: they show what the agent caught before a human would
have, and the before/after on a single revision is the clearest demonstration
that a critic loop does real work rather than decorating a single prompt.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from agent import critic, writer
from agent.angles import ANGLES
from agent.brief import build_brief
from agent.llm import LLM

MAX_ROUNDS = 3


def run_angle(llm: LLM, brief: dict, angle_key: str, verbose: bool = True) -> dict:
    """Draft and revise one angle until it passes review or the budget is spent."""
    rounds = []
    text = None
    rev = None

    for n in range(1, MAX_ROUNDS + 1):
        if n == 1:
            text = writer.draft(llm, brief, angle_key)
        else:
            text = writer.draft(
                llm,
                brief,
                angle_key,
                previous=text,
                verdict=rev.get("verdict"),
                failures=rev.get("failures", []),
            )

        rev = critic.review(llm, brief, angle_key, text)
        rounds.append(
            {
                "round": n,
                "draft": text,
                "passed": rev["passed"],
                "mean_score": rev["mean_score"],
                "hard_fails": rev["hard_fails_tripped"],
                "unsupported_claims": rev.get("unsupported_claims_found", []),
                "verdict": rev.get("verdict"),
                "failures": rev.get("failures", []),
                "scores": rev.get("scores", {}),
            }
        )

        if verbose:
            mark = "PASS" if rev["passed"] else "REJECT"
            hf = (
                f"  hard fails: {', '.join(rev['hard_fails_tripped'])}"
                if rev["hard_fails_tripped"]
                else ""
            )
            print(
                f"    round {n}: {mark}  score {rev['mean_score']}{hf}\n"
                f"      \"{rev.get('verdict', '')}\""
            )

        if rev["passed"]:
            break

    return {
        "angle": angle_key,
        "angle_name": ANGLES[angle_key]["name"],
        "rounds": rounds,
        "final_draft": text,
        "final_score": rev["mean_score"],
        "shipped": rev["passed"],
        "rounds_used": len(rounds),
    }


def run_prospect(
    llm: LLM, prospect_id: str, angle_keys: list[str], verbose: bool = True
) -> dict:
    brief = build_brief(prospect_id)
    if verbose:
        m = brief["measured"]
        print(f"\n{brief['name']}  ({brief['vertical']})")
        print(
            f"  brief: {m['substantive_reviews']} substantive reviews, "
            f"support {m['support_share_of_substantive']}, "
            f"channel-failure {m['channel_failure_share_of_negative']}, "
            f"rank {m['pain_rank']}/{m['pain_rank_of']}, "
            f"{len(brief['verbatim_quotes'])} quotes"
        )

    results = []
    for ak in angle_keys:
        if verbose:
            print(f"  angle: {ANGLES[ak]['name']}")
        results.append(run_angle(llm, brief, ak, verbose=verbose))

    shipped = [r for r in results if r["shipped"]]
    winner = max(shipped or results, key=lambda r: r["final_score"])

    return {
        "prospect_id": prospect_id,
        "name": brief["name"],
        "vertical": brief["vertical"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "brief": brief,
        "angles": results,
        "winning_angle": winner["angle"],
        "winning_score": winner["final_score"],
        "any_shipped": bool(shipped),
    }
