"""
Research brief construction.

THE CENTRAL CONSTRAINT OF THIS WHOLE AGENT
-------------------------------------------
The writer may only use facts that appear in the brief. The brief is built
from measured data - never from the model's own knowledge of the company.

This is not pedantry. An LLM asked to write a personalised outreach email to
"PolicyBazaar" will happily produce fluent sentences about their funding round,
their market position and their strategic priorities, drawn from training data
that is stale, half-remembered, or wrong. The recipient is the one person on
earth guaranteed to notice. One hallucinated fact about someone's own company
destroys the entire message, and in BFSI it can be worse than embarrassing.

So the brief is a closed world. Everything in it traces to:
  - the collected review corpus (counts, shares, verbatim quotes)
  - the prospect record (vertical, regulator - static classification)
  - the eval harness results (our own measured output)

And the critic (critic.py) hard-fails any draft containing a specific claim
that is not in the brief it was given.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MAX_QUOTES = 4
QUOTE_MAX_CHARS = 180


def _load(name: str) -> dict:
    p = ROOT / "out" / name
    if not p.exists():
        raise SystemExit(
            f"Missing {p}. Run the pipeline first:\n"
            "  python -m src.collect_playstore && python -m src.classify "
            "&& python -m src.score && python -m src.run_evals"
        )
    return json.loads(p.read_text())


def build_brief(prospect_id: str) -> dict:
    """Assemble every measured fact we hold about one prospect."""
    pipeline = _load("pipeline.json")
    classified = _load("signals_classified.json")
    evals = _load("evals.json")

    row = next(
        (r for r in pipeline["pipeline"] if r["prospect_id"] == prospect_id), None
    )
    if not row:
        raise SystemExit(f"No prospect '{prospect_id}' in pipeline.json")

    # Regulator lives in the prospect universe, not in the scored row. It
    # matters to the brief because compliance-grade conversation logging is a
    # buying requirement for a SEBI/RBI/IRDAI entity rather than a nice-to-have.
    import yaml

    universe = yaml.safe_load((ROOT / "data" / "prospects.yaml").read_text())["prospects"]
    static = next((p for p in universe if p["id"] == prospect_id), {})
    summary = next(
        (s for s in classified["summaries"] if s["prospect_id"] == prospect_id), {}
    )

    sig = summary.get("signals", {})
    smp = summary.get("sample", {})

    quotes = []
    for e in sorted(summary.get("evidence", []), key=lambda x: len(x.get("text", "")))[
        :MAX_QUOTES
    ]:
        t = (e.get("text") or "").strip()
        quotes.append(
            {"stars": e.get("score"), "text": t[:QUOTE_MAX_CHARS]}
        )

    # Peer context: where this prospect sits in the measured distribution.
    # A share means little alone; "4th highest of 19 measured" is a fact a
    # senior operator can act on.
    scored = [
        (r["prospect_id"], r["name"], r.get("pain_intensity"))
        for r in pipeline["pipeline"]
        if r.get("pain_intensity") is not None
    ]
    scored.sort(key=lambda t: -(t[2] or 0))
    rank = next((i + 1 for i, t in enumerate(scored) if t[0] == prospect_id), None)

    base = evals["baseline_retrieval"]
    integ = evals["routed_integrated"]

    return {
        "prospect_id": prospect_id,
        "name": row["name"],
        "vertical": row.get("vertical") or static.get("vertical"),
        "regulators": static.get("regulator", []),
        "measured": {
            "reviews_fetched": smp.get("reviews_fetched"),
            "substantive_reviews": smp.get("substantive"),
            "negative_substantive_reviews": smp.get("negative_substantive"),
            "support_share_of_substantive": sig.get("support_review_share"),
            "channel_failure_share_of_negative": sig.get("unresolved_language_share"),
            "pain_rank": rank,
            "pain_rank_of": len(scored),
            "confidence": row.get("confidence"),
        },
        "verbatim_quotes": quotes,
        "our_own_eval": {
            "cases": base["n"],
            "naive_automated_pct": base["pct_automated"],
            "naive_correct_pct": base["pct_correct"],
            "naive_confidently_wrong": base["confidently_wrong"],
            "integrated_automated_pct": integ["pct_automated"],
            "integrated_correct_pct": integ["pct_correct"],
            "integrated_confidently_wrong": integ["confidently_wrong"],
        },
        "collection_date": "2026-10-20",
        "source": "public Google Play Store reviews, India storefront",
        "known_gaps": [
            "No contact volume data - review share is directional only",
            "Single snapshot, no month-over-month trend",
            "App reviews skew toward angry and resolved-badly customers",
        ],
    }


def brief_as_prompt(brief: dict) -> str:
    """Render the brief as the closed world the writer is allowed to draw on."""
    m = brief["measured"]
    lines = [
        f"COMPANY: {brief['name']}",
        f"VERTICAL: {brief['vertical']}  REGULATORS: {', '.join(brief['regulators'])}",
        "",
        "MEASURED FACTS (collected "
        f"{brief['collection_date']} from {brief['source']}):",
        f"- {m['reviews_fetched']} recent reviews fetched; "
        f"{m['substantive_reviews']} carried substantive text",
        f"- {m['negative_substantive_reviews']} of those were negative (1-2 stars)",
    ]
    if m["support_share_of_substantive"] is not None:
        lines.append(
            f"- {m['support_share_of_substantive']:.1%} of substantive reviews are "
            "support-related"
        )
    if m["channel_failure_share_of_negative"] is not None:
        lines.append(
            f"- {m['channel_failure_share_of_negative']:.1%} of negative reviews cite "
            "the SUPPORT CHANNEL failing (no response, ticket unanswered, repeated "
            "follow-up) rather than the product itself"
        )
    if m["pain_rank"]:
        lines.append(
            f"- ranks {m['pain_rank']} of {m['pain_rank_of']} measured companies on "
            "support pain"
        )

    lines += ["", "VERBATIM CUSTOMER QUOTES (real, public, checkable):"]
    for q in brief["verbatim_quotes"]:
        lines.append(f'  [{q["stars"]}*] "{q["text"]}"')

    e = brief["our_own_eval"]
    lines += [
        "",
        f"OUR OWN EVAL RESULT (on {e['cases']} real support queries from this domain):",
        f"- a naive retrieval bot automated {e['naive_automated_pct']:.0f}% of them, "
        f"disposed {e['naive_correct_pct']:.0f}% correctly, and was confidently wrong "
        f"{e['naive_confidently_wrong']} times",
        f"- routing + system integration automated "
        f"{e['integrated_automated_pct']:.0f}%, disposed "
        f"{e['integrated_correct_pct']:.0f}% correctly, {e['integrated_confidently_wrong']} "
        "confidently wrong",
        "- near-identical deflection rate, very different correctness",
        "",
        "KNOWN GAPS IN THIS DATA (do not paper over these):",
    ]
    lines += [f"- {g}" for g in brief["known_gaps"]]
    return "\n".join(lines)
