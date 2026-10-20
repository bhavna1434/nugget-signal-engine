"""
Support-pain classifier.

Turns raw app reviews into the four pain signals the scoring engine consumes.

WHY A KEYWORD TAXONOMY AND NOT AN LLM
--------------------------------------
An LLM classifier here would be slower, cost money per run, be
non-deterministic across runs, and - the real problem - be unauditable. When a
prospect asks "how did you conclude that about my support operation?", the
answer needs to be a rule you can point at, not "the model felt so".

The taxonomy below is the asset. It encodes which complaints in Indian BFSI
indicate a SUPPORT-CHANNEL failure as opposed to general product
dissatisfaction - a distinction that decides whether Nugget is relevant at all.
A one-star review saying "app is slow" is not a Nugget opportunity.
A one-star review saying "raised ticket 12 days ago, no response" is.

The hard-query taxonomy (HARD_QUERY) is the differentiated part: these are the
query classes that generic retrieval-based support bots fail on, because the
answer depends on regulation, on the specific instrument, and on the user's own
tax position rather than on a documented FAQ. They are also the classes where a
wrong answer creates regulatory exposure for the operator - which is precisely
why those queries stay with human agents and why the support cost never falls.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# TAXONOMY
# ---------------------------------------------------------------------------

# Tier 1: the review is about the SUPPORT CHANNEL, not the product.
# This is the signal that makes a prospect relevant to Nugget at all.
UNRESOLVED = [
    r"\bno (?:one |body )?(?:response|reply|replies|replied|answer|answering)\b",
    r"\bnot? (?:getting|received) (?:any )?(?:response|reply|revert)\b",
    r"\braised? (?:a )?(?:ticket|complaint|query|grievance|request)\b",
    r"\bticket (?:is )?(?:still )?(?:open|pending|unresolved)\b",
    r"\b(?:calling|called|emailed|mailed|writing|written) (?:them )?(?:for|since)\b",
    r"\bcustomer (?:care|support|service) (?:is )?(?:useless|pathetic|worst|horrible|terrible|not responding|never)\b",
    r"\bno (?:resolution|update|action)\b",
    r"\b(?:\d+|many|several) (?:days|weeks|months) (?:and |but )?(?:still |no )\b",
    r"\bfollow(?:ing)? up (?:since|for|repeatedly)\b",
    r"\bchat ?bot (?:is )?(?:useless|useless|not helpful|doesn'?t|cannot|can'?t)\b",
    r"\bnever (?:pick|picks|picked|answer|answers|answered) (?:the |up )?(?:call|phone)\b",
    r"\bauto(?:mated)? (?:reply|response) (?:only|every time)\b",
    r"\bescalat(?:e|ed|ion)\b",
]

# Tier 2: support-adjacent - a service issue that generates a contact.
# Broader than Tier 1; indicates contact volume rather than channel failure.
SUPPORT_RELATED = UNRESOLVED + [
    r"\bkyc\b",
    r"\bverif(?:y|ication|ied)\b",
    r"\bwithdraw(?:al|n|ing)?\b",
    r"\brefund\b",
    r"\bstuck\b",
    r"\bpending\b",
    r"\bblocked\b",
    r"\bdeduct(?:ed|ion)?\b",
    r"\bnot credited\b",
    r"\bunable to\b",
    r"\bcan'?t (?:login|log in|access|withdraw|redeem)\b",
    r"\bdocument(?:s)? (?:rejected|not accepted|upload)\b",
    r"\baccount (?:freeze|frozen|blocked|closed)\b",
    r"\bhelp ?(?:line|desk)\b",
    r"\bgrievance\b",
    r"\bcomplaint\b",
]

# Tier 3: the differentiated wedge.
# Query classes where the correct answer depends on regulation + instrument +
# the individual's tax position. Generic retrieval bots fail these because the
# answer is not in an FAQ - it is a computation over the user's own position.
# Getting one wrong is a mis-selling / mis-statement exposure for the operator.
HARD_QUERY = {
    "tds_withholding": [
        r"\btds\b",
        r"\btax deducted\b",
        r"\b15 ?g\b", r"\b15 ?h\b",
        r"\bform 16\b", r"\bform 26as\b",
        r"\bais\b",
        r"\bwithholding\b",
        r"\btax certificate\b",
    ],
    "repayment_mechanics": [
        r"\brepayment\b",
        r"\bprincipal (?:repaid|repayment|return)\b",
        r"\binterest (?:not )?(?:credited|received|payout|payment)\b",
        r"\bcoupon\b",
        r"\bpayout (?:date|schedule|delay)\b",
        r"\bemi (?:schedule|date)\b",
        r"\bamortis|amortiz",
    ],
    "maturity_settlement": [
        r"\bmaturity\b",
        r"\bmatured\b",
        r"\bredemption\b",
        r"\bredeem(?:ed)?\b",
        r"\bsettlement (?:date|cycle|delay)\b",
        r"\bt\+\d\b",
    ],
    "yield_confusion": [
        r"\bxirr\b",
        r"\birr\b",
        r"\byield\b",
        r"\bytm\b",
        r"\breturns? (?:shown|displayed|calculated|different|mismatch)\b",
        r"\bpost.?tax return\b",
    ],
    "regulatory_status": [
        r"\bsebi\b", r"\brbi\b", r"\birdai\b",
        r"\bscores\b",
        r"\bombudsman\b",
        r"\bnominee\b", r"\bnomination\b",
        r"\bdemat\b",
        r"\bckyc\b",
    ],
}

# Hindi / Hinglish complaint vocabulary.
#
# Added after the first real collection run: the corpus contains Devanagari
# reviews (a long PolicyBazaar grievance among them) that an English-only
# regex scored as neutral. In Indian consumer apps this is not an edge case.
# Romanised Hinglish is at least as common as Devanagari.
#
# PRECISION NOTE - these must be CHANNEL-specific, not merely negative.
#
# The first version of this list included ghatiya, bekar, bakwas, raddi,
# pareshan and dhokha. Those mean "rubbish", "useless", "annoyed", "cheated" -
# they are generic product abuse and say nothing about whether support
# responded. Including them inflated unresolved_language_share with ordinary
# dissatisfaction, and the message generator then quoted "ye sab se bekar app
# ha" back at a prospect as evidence their SUPPORT was failing.
#
# The whole value of this metric is the distinction between "your product
# disappointed me" and "I could not get an answer from you". A pattern that
# does not preserve that distinction belongs in SUPPORT_RELATED at most, and
# usually nowhere.
UNRESOLVED_HI = [
    r"कोई\s*(?:जवाब|उत्तर|रिस्पांस|response)\s*नहीं",
    r"जवाब\s*नहीं\s*(?:मिला|दिया|आया)?",
    r"कोई\s*(?:सुनवाई|समाधान)\s*नहीं",
    r"शिकायत\s*(?:की|दर्ज|करने)",
    r"कस्टमर\s*(?:केयर|सपोर्ट)\s*(?:से|कोई|नहीं)",
    r"फोन\s*(?:नहीं\s*उठाते|नहीं\s*उठाया)",
    # romanised — each one is about a response that did not arrive
    r"\bkoi\s+(?:jawab|response|reply|sunwai|samadhan)\s+nahi",
    r"\bjawab\s+nahi\b",
    r"\bresponse\s+nahi\b",
    r"\bcall\s+(?:nahi\s+uthat|receive\s+nahi)",
    r"\bcomplaint\s+ki\b.*\bnahi\b",
    r"\bticket\s+raise\s+ki\b",
]

# A review has to carry actual text before it can tell us anything about a
# support operation. The first real run found a MEDIAN review length of 13
# characters and 63% of reviews under 25 - "nice", "good app", an emoji.
# Including those in the denominator was the single worst methodological error
# in the first version: it diluted every pain score by roughly 5x and made
# every prospect look healthy.
SUBSTANTIVE_MIN_CHARS = 40

# Minimum sample before a share is meaningful. Below these, the signal is
# recorded as None rather than as a number, which reduces confidence rather
# than inventing precision. Navi returned 16 substantive reviews in the first
# run; a "12.5% support share" off 16 reviews is two reviews and a rounding
# error, and ranking a prospect on it would repeat the confidence bug one
# layer down.
MIN_SUBSTANTIVE_FOR_SIGNAL = 40
MIN_NEGATIVE_FOR_SIGNAL = 25

_RATING_DROP_WINDOW = 50  # reviews; compares newest N vs previous N


def _compile(patterns: list[str]) -> re.Pattern:
    return re.compile("|".join(patterns), re.IGNORECASE)


RE_UNRESOLVED = _compile(UNRESOLVED + UNRESOLVED_HI)
RE_SUPPORT = _compile(SUPPORT_RELATED + UNRESOLVED_HI)
RE_HARD = {k: _compile(v) for k, v in HARD_QUERY.items()}


def classify_review(text: str) -> dict:
    """Classify a single review. Returns which tiers it matched."""
    text = text or ""
    hard_hits = [name for name, rx in RE_HARD.items() if rx.search(text)]
    return {
        "unresolved": bool(RE_UNRESOLVED.search(text)),
        "support_related": bool(RE_SUPPORT.search(text)),
        "hard_queries": hard_hits,
    }


def _rating_trend(reviews: list[dict]) -> float | None:
    """
    Change in mean rating: newest window vs the window before it.
    Negative = deteriorating. None if not enough data to be meaningful.
    """
    scored = [r for r in reviews if isinstance(r.get("score"), (int, float))]
    if len(scored) < _RATING_DROP_WINDOW * 2:
        return None
    newest = scored[:_RATING_DROP_WINDOW]
    previous = scored[_RATING_DROP_WINDOW : _RATING_DROP_WINDOW * 2]
    mean_new = sum(r["score"] for r in newest) / len(newest)
    mean_prev = sum(r["score"] for r in previous) / len(previous)
    return round(mean_new - mean_prev, 3)


def summarise(record: dict) -> dict:
    """
    Turn one collector record into the signal inputs the scorer consumes.

    Returns None-valued signals when the collector did not produce usable data.
    Never substitutes a default. A None here propagates into a lower confidence
    multiplier downstream, which is the intended behaviour.
    """
    out = {
        "prospect_id": record["prospect_id"],
        "name": record["name"],
        "collector_status": record.get("status"),
        "collector_reason": record.get("status_reason"),
        "signals": {
            # share of SUBSTANTIVE reviews that are support-related
            "support_review_share": None,
            # share of NEGATIVE SUBSTANTIVE reviews citing channel failure.
            # Framed this way the metric answers a question worth asking:
            # among customers unhappy enough to write at length, how many are
            # unhappy about the support channel rather than the product?
            "unresolved_language_share": None,
            "rating_trend": None,
            "review_volume": None,   # substantive count, not raw count
        },
        "sample": {},
        "hard_query_counts": {},
        "evidence": [],
        "signals_collected": 0,
    }

    if record.get("status") != "ok":
        return out

    reviews = record.get("reviews") or []
    n = len(reviews)
    if n == 0:
        out["collector_reason"] = "status ok but zero reviews present"
        return out

    # Restrict to reviews carrying enough text to say anything at all.
    substantive = [r for r in reviews if len(r.get("content") or "") >= SUBSTANTIVE_MIN_CHARS]
    negative = [r for r in substantive if (r.get("score") or 5) <= 2]

    out["sample"] = {
        "reviews_fetched": n,
        "substantive": len(substantive),
        "negative_substantive": len(negative),
        "substantive_share": round(len(substantive) / n, 3),
    }

    support_n = 0
    unresolved_n = 0
    hard_counts: dict[str, int] = {}
    evidence: list[dict] = []

    for r in substantive:
        text = r.get("content") or ""
        c = classify_review(text)
        if c["support_related"]:
            support_n += 1

    for r in negative:
        text = r.get("content") or ""
        c = classify_review(text)
        # Hard-query topics are counted over NEGATIVE reviews only.
        #
        # The first version counted them over all substantive reviews, which
        # matched on the topic word regardless of sentiment. Against real data
        # that scored "Easy dashboard shows upcoming repayment schedules" (Grip
        # Invest, 5 stars) as evidence of repayment pain, and "Quick-filter
        # tags like 'High Yield'" as yield confusion. The counter was measuring
        # what an app is ABOUT, not what customers struggle with - and it would
        # have put a prospect's own five-star reviews into an email telling
        # them their support was failing.
        for h in c["hard_queries"]:
            hard_counts[h] = hard_counts.get(h, 0) + 1
        if c["unresolved"]:
            unresolved_n += 1
            # Keep the highest-signal examples as citable evidence. Outreach
            # that references a real public review is credible; outreach that
            # references an aggregate is not.
            if len(evidence) < 8:
                evidence.append(
                    {
                        "score": r.get("score"),
                        "at": r.get("at"),
                        "text": text[:400],
                        "hard_queries": c["hard_queries"],
                    }
                )

    # Below the minimum sample, record None rather than a number. A share
    # computed over 16 reviews is not a measurement of a support operation.
    if len(substantive) >= MIN_SUBSTANTIVE_FOR_SIGNAL:
        out["signals"]["support_review_share"] = round(support_n / len(substantive), 4)
        out["signals"]["review_volume"] = len(substantive)
    else:
        out["collector_reason"] = (
            f"only {len(substantive)} substantive reviews "
            f"(min {MIN_SUBSTANTIVE_FOR_SIGNAL}) - sample too small to score"
        )

    if len(negative) >= MIN_NEGATIVE_FOR_SIGNAL:
        out["signals"]["unresolved_language_share"] = round(unresolved_n / len(negative), 4)

    out["signals"]["rating_trend"] = _rating_trend(reviews)
    out["hard_query_counts"] = dict(
        sorted(hard_counts.items(), key=lambda kv: kv[1], reverse=True)
    )
    out["evidence"] = evidence
    out["signals_collected"] = sum(
        1 for v in out["signals"].values() if v is not None
    )
    return out


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=str(ROOT / "out" / "signals_playstore.json"))
    ap.add_argument("--out", dest="outp", default=str(ROOT / "out" / "signals_classified.json"))
    args = ap.parse_args()

    payload = json.loads(Path(args.inp).read_text())
    summaries = [summarise(r) for r in payload["records"]]

    result = {
        "source_file": args.inp,
        "source_reachable": payload.get("source_reachable"),
        "synthetic": payload.get("synthetic", False),
        "summaries": summaries,
    }
    Path(args.outp).write_text(json.dumps(result, indent=2))

    usable = sum(1 for s in summaries if s["signals_collected"] > 0)
    print(f"{usable}/{len(summaries)} prospects produced usable signals -> {args.outp}")
    print(
        f"\n{'prospect':<16}{'fetched':>9}{'subst':>7}{'neg':>6}"
        f"{'support':>9}{'unresolved':>12}"
    )
    print("-" * 59)

    def pct(v):
        # Signals are None when the sample was too small to measure. Print
        # that as '--' rather than formatting None, and never as 0%, which
        # would read as 'measured, and found nothing'.
        return "--" if v is None else f"{v:.1%}"

    for s in summaries:
        sig, smp = s["signals"], s.get("sample") or {}
        if not s["signals_collected"]:
            print(f"{s['prospect_id']:<16}  NO SIGNAL ({s['collector_reason']})")
            continue
        print(
            f"{s['prospect_id']:<16}{smp.get('reviews_fetched', 0):>9}"
            f"{smp.get('substantive', 0):>7}{smp.get('negative_substantive', 0):>6}"
            f"{pct(sig['support_review_share']):>9}"
            f"{pct(sig['unresolved_language_share']):>12}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
