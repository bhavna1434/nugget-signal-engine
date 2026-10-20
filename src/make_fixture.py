"""
Synthetic fixture generator - FOR PIPELINE TESTING ONLY.

WHY THIS FILE EXISTS AND WHY IT IS DANGEROUS
---------------------------------------------
The Play Store is unreachable from the build sandbox, so the downstream
pipeline (classifier -> scorer -> message generator) cannot be developed or
tested against real data here. This generates review text with known
statistical properties so the pipeline can be verified.

THIS DATA IS NOT REAL. It describes no actual company's support operation.

Every artefact derived from it is stamped `"synthetic": true`, and
src/generate_messages.py REFUSES to produce outreach copy from a synthetic
chain unless --i-know-this-is-fake is passed explicitly.

That guard is the point. The failure mode this prevents is a plausible-looking
pipeline producing a personalised message citing a complaint statistic that
was never measured, which then reaches a real prospect. That is not a bug, it
is a fabricated claim about a named company's operations sent to that company.

Run the real collector before anything leaves this repo:
    python -m src.collect_playstore
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SEED = 20261020

# Templates deliberately mirror the register of real Indian app-store reviews,
# including the hard-query vocabulary the classifier is built to detect.
UNRESOLVED_T = [
    "Raised a ticket {n} days ago, still no response from customer care.",
    "Calling their helpline since last week, nobody picks up the call.",
    "Worst customer support. Only automated reply every time, no resolution.",
    "I have emailed them 4 times about my {topic}, no revert at all.",
    "Chatbot is useless, cannot understand my query about {topic}. Need human agent.",
    "Complaint raised on {n} th, ticket still open, no update from support team.",
    "Escalated twice, still waiting. Pathetic service.",
]
HARD_T = [
    "TDS has been deducted on my interest but Form 26AS is not showing it, support not responding.",
    "Submitted 15G form but TDS still deducted, raised ticket no response.",
    "My repayment was due on 5th, interest not credited yet, no one replies.",
    "Principal repayment not received after maturity, calling since 10 days.",
    "XIRR shown in app does not match actual returns, asked support, no clarity.",
    "Coupon payout delayed again, customer care says wait, no timeline given.",
    "Bond matured last month, redemption amount still pending, grievance raised.",
    "Why is yield different from what was shown at the time of investment?",
    "KYC rejected 3 times without reason, CKYC already done, support unhelpful.",
]
NEUTRAL_T = [
    "Good app, easy to use interface.",
    "Decent returns so far, happy with the experience.",
    "App is slow sometimes but overall fine.",
    "Nice UI, smooth onboarding process.",
    "Works well, no complaints.",
    "Charges are a bit high compared to others.",
    "App crashes occasionally on my phone.",
]
TOPICS = ["withdrawal", "KYC", "TDS certificate", "maturity amount", "refund", "interest payout"]

# Per-prospect synthetic pain level. NOT a claim about these companies -
# arbitrary values chosen to exercise the full range of the scorer.
PAIN_PROFILE = {
    "high": 0.46,
    "medium": 0.26,
    "low": 0.11,
}


def build_reviews(rng: random.Random, pain: float, n: int) -> list[dict]:
    out = []
    now = datetime.now(timezone.utc)
    for i in range(n):
        roll = rng.random()
        if roll < pain * 0.55:
            text = rng.choice(UNRESOLVED_T).format(n=rng.randint(2, 30), topic=rng.choice(TOPICS))
            score = rng.choice([1, 1, 1, 2])
        elif roll < pain:
            text = rng.choice(HARD_T)
            score = rng.choice([1, 2, 2])
        else:
            text = rng.choice(NEUTRAL_T)
            score = rng.choice([3, 4, 4, 5, 5])
        out.append(
            {
                "score": score,
                "content": text,
                "at": (now - timedelta(hours=i * 3)).isoformat(),
                "thumbs_up": rng.randint(0, 40),
            }
        )
    return out


def main() -> int:
    rng = random.Random(SEED)
    prospects = yaml.safe_load((ROOT / "data" / "prospects.yaml").read_text())["prospects"]

    records = []
    for p in prospects:
        if not p.get("android_package"):
            records.append(
                {
                    "prospect_id": p["id"],
                    "name": p["name"],
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                    "source": "SYNTHETIC",
                    "package": None,
                    "status": "not_applicable",
                    "status_reason": "prospect has no Android app (web-primary product)",
                    "app_meta": None,
                    "reviews": None,
                    "review_count_collected": 0,
                }
            )
            continue

        band = rng.choices(["high", "medium", "low"], weights=[3, 4, 3])[0]
        # Bond platforms skewed higher to exercise the hard-query path.
        if p.get("sub_vertical") == "bonds_fixed_income":
            band = rng.choices(["high", "medium"], weights=[3, 1])[0]
        pain = PAIN_PROFILE[band]
        n = rng.randint(140, 300)
        revs = build_reviews(rng, pain, n)

        records.append(
            {
                "prospect_id": p["id"],
                "name": p["name"],
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "source": "SYNTHETIC",
                "package": p["android_package"],
                "status": "ok",
                "status_reason": f"SYNTHETIC fixture, {n} generated reviews, band={band}",
                "app_meta": {
                    "rating": round(sum(r["score"] for r in revs) / len(revs), 2),
                    "ratings_count": None,
                    "reviews_count": n,
                    "installs": None,
                    "updated": None,
                },
                "reviews": revs,
                "review_count_collected": n,
            }
        )

    out = ROOT / "out" / "signals_playstore.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "source_reachable": False,
                "reachability_reason": "SYNTHETIC FIXTURE - no network call was made",
                "synthetic": True,
                "WARNING": (
                    "This data is fabricated for pipeline testing. It describes no real "
                    "company's support operation. Do not derive any outbound claim from it."
                ),
                "seed": SEED,
                "records": records,
            },
            indent=2,
        )
    )
    print(f"SYNTHETIC fixture written -> {out}")
    print(f"  {sum(1 for r in records if r['status']=='ok')} prospects with generated reviews")
    print("  Run `python -m src.collect_playstore` on a networked machine to replace it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
