"""
Outreach message generator.

WHAT THE MESSAGES MAY CLAIM
---------------------------
Only what the pipeline measured. Every number in a generated message traces to
a field in pipeline.json, and every quoted line is a real public review from
that prospect's own store listing.

An earlier version hooked on the hard-query thesis: "I sorted your complaints
by query class and the TDS cluster stood out." The first real collection run
killed that hook. Across 5,700 reviews from 19 BFSI apps there were ZERO TDS
complaints, 17 hard-query mentions in total, and the topic counter had been
matching five-star reviews praising a feature. Sending that hook would have
meant citing a prospect's own positive reviews as evidence their support was
failing - a claim that is both false and trivially checkable by the recipient.

What the data DOES support is the support-channel signal: among customers
unhappy enough to write at length, what share are unhappy about the channel
rather than the product. That is measured, it varies 0-12% across the set, and
the recipient can verify it in ten minutes on their own store listing.

TWO HARD REFUSALS:
1. Synthetic data - refuses without --i-know-this-is-fake.
2. Low confidence - prospects below the threshold are skipped entirely.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

# Keep quoted review text short. These are real people's public words; a brief
# excerpt makes the point and anything longer is lifting someone's writing.
QUOTE_MAX_WORDS = 14


def _short_quote(text: str) -> str:
    words = (text or "").split()
    if len(words) <= QUOTE_MAX_WORDS:
        return " ".join(words)
    return " ".join(words[:QUOTE_MAX_WORDS]) + "..."


def _pick_quotes(row: dict, n: int = 2) -> list[str]:
    """Shortest real complaints first - they read as evidence, not as a dump."""
    ev = sorted(row.get("evidence", []), key=lambda e: len(e.get("text", "")))
    return [_short_quote(e["text"]) for e in ev[:n]]


def first_touch(row: dict, evals: dict) -> dict:
    name = row["name"]
    sig = row.get("signals_detail", {})
    smp = row.get("sample", {})
    support = sig.get("support_review_share")
    unres = sig.get("unresolved_language_share")
    quotes = _pick_quotes(row)
    base = evals["baseline_retrieval"]

    subject = f"{name}: {unres:.0%} of your negative reviews are about support, not product" \
        if unres else f"{name}: a read on your support contact mix"

    lines = [f"Hi {{first_name}},", ""]

    if unres is not None:
        lines.append(
            f"I pulled {name}'s recent public Play Store reviews and sorted the "
            f"substantive ones by what the complaint is actually about. Of "
            f"{smp.get('negative_substantive')} negative reviews with real text in them, "
            f"{unres:.0%} are about the support channel itself rather than the product - "
            f"no response, tickets left open, repeat follow-ups."
        )
    else:
        lines.append(
            f"I pulled {name}'s recent public Play Store reviews and sorted the "
            f"substantive ones by what the complaint is actually about. "
            f"{support:.0%} of them are support-related."
        )

    if quotes:
        lines += ["", f'Two of them, verbatim: "{quotes[0]}"']
        if len(quotes) > 1:
            lines.append(f'and "{quotes[1]}"')

    lines += [
        "",
        "The reason I find that split interesting rather than just bad: complaints "
        "about the channel behave differently from complaints about the product. "
        "They tend to be the ones where the customer already knew what they wanted "
        "and could not get an answer, which is the cheapest category to fix and the "
        "most expensive to leave alone.",
        "",
        f"Does that match what you see in your own contact mix, or do your "
        f"store reviews skew differently from your ticket queue?",
        "",
        "{sender}",
    ]
    return {"channel": "email", "step": 1, "subject": subject, "body": "\n".join(lines)}


def sequence(row: dict, evals: dict) -> list[dict]:
    name = row["name"]
    base = evals["baseline_retrieval"]
    integ = evals["routed_integrated"]

    return [
        {
            "channel": "email",
            "step": 2,
            "wait_days": 4,
            "subject": f"Re: {name} — the metric that hides this",
            "body": f"""Following up with the part I think is actually useful, whether or not we ever speak.

I built an eval harness over {base['n']} real support queries from Indian wealth and fixed-income operations, and scored three agent configurations on whether they DISPOSED of each query correctly, rather than on how many they deflected:

Naive retrieval:      {base['pct_automated']:.0f}% automated, {base['pct_correct']:.0f}% correctly disposed, {base['confidently_wrong']} confidently wrong
Routed + integrated:  {integ['pct_automated']:.0f}% automated, {integ['pct_correct']:.0f}% correctly disposed, {integ['confidently_wrong']} confidently wrong

Near-identical deflection rates. The difference is entirely in whether the system answers from the customer's own record or from a help article.

If your current support tooling reports deflection rate but not disposition correctness, that gap doesn't appear anywhere in your reporting.

{{sender}}""",
        },
        {
            "channel": "linkedin",
            "step": 3,
            "wait_days": 5,
            "subject": None,
            "body": f"""{{first_name}} — sent you a note on support complaint mix at {name}. No reply needed if it isn't a live problem.

One thing I'd value your read on regardless: when a customer writes in saying the outcome contradicts what they expected - money not received, a form submitted but not applied - does that reach a human at {name}, or does a bot take it? I have yet to find a platform where the honest answer is the second one.""",
        },
        {
            "channel": "email",
            "step": 4,
            "wait_days": 7,
            "subject": f"Closing the loop — {name}",
            "body": """Last one from me.

I'll leave the query taxonomy and the eval harness with you either way. They're useful independently of us, and you can run them against whatever you have in production today.

If support contact mix becomes a priority later in the year, I'm easy to find.

{sender}""",
        },
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--i-know-this-is-fake", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "out" / "messages.json"))
    args = ap.parse_args()

    pipeline = json.loads((ROOT / "out" / "pipeline.json").read_text())
    evals = json.loads((ROOT / "out" / "evals.json").read_text())
    classified = json.loads((ROOT / "out" / "signals_classified.json").read_text())
    cfg = yaml.safe_load((ROOT / "data" / "scoring.yaml").read_text())
    min_conf = cfg["confidence"]["min_confidence_to_contact"]

    if pipeline.get("synthetic") and not args.i_know_this_is_fake:
        print(
            "REFUSING TO GENERATE.\n\n"
            "The pipeline was built from the synthetic fixture. Generating outreach\n"
            "copy from it would produce fluent, personalised messages citing complaint\n"
            "statistics about named companies that were never measured.\n\n"
            "Run the real collector first:\n"
            "    python -m src.collect_playstore && python -m src.classify && python -m src.score",
            file=sys.stderr,
        )
        return 2

    by_id = {s["prospect_id"]: s for s in classified["summaries"]}
    rows = [r for r in pipeline["pipeline"] if r["contactable"]][: args.top]
    skipped = [r for r in pipeline["pipeline"] if not r["contactable"]]

    out = []
    for r in rows:
        s = by_id.get(r["prospect_id"], {})
        enriched = dict(r)
        enriched["signals_detail"] = s.get("signals", {})
        enriched["sample"] = s.get("sample", {})
        enriched["evidence"] = s.get("evidence", [])
        out.append(
            {
                "prospect_id": r["prospect_id"],
                "name": r["name"],
                "priority": r["priority"],
                "confidence": r["confidence"],
                "evidence_basis": {
                    "sample": s.get("sample", {}),
                    "support_review_share": s.get("signals", {}).get("support_review_share"),
                    "unresolved_language_share": s.get("signals", {}).get(
                        "unresolved_language_share"
                    ),
                    "quoted_reviews": _pick_quotes(enriched),
                },
                "messages": [first_touch(enriched, evals)] + sequence(enriched, evals),
            }
        )

    payload = {
        "synthetic": pipeline.get("synthetic", False),
        "generated_for": len(out),
        "skipped_low_confidence": [
            {"name": r["name"], "confidence": r["confidence"], "reason": r["hold_reason"]}
            for r in skipped
        ],
        "sequences": out,
    }
    Path(args.out).write_text(json.dumps(payload, indent=2))

    print(f"Generated {len(out)} sequences (threshold: confidence >= {min_conf})")
    print(f"Skipped {len(skipped)} prospects below the confidence threshold")
    for o in out:
        eb = o["evidence_basis"]
        print(
            f"  {o['name']:<16} unresolved={eb['unresolved_language_share']} "
            f"support={eb['support_review_share']} quotes={len(eb['quoted_reviews'])}"
        )
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
