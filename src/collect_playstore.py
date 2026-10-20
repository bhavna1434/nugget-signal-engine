"""
Play Store signal collector.

Collects review-derived support-pain signals for each prospect.

DESIGN NOTE — why this file is defensive to the point of paranoia
-----------------------------------------------------------------
During development, google_play_scraper.reviews() returned an EMPTY LIST with
no exception when the network was blocked by a proxy, while app() on the same
package raised URLError 403 on the same call stack.

An empty list is indistinguishable from "this app genuinely has no recent
reviews" unless you check. If we had trusted it, the engine would have scored
every prospect as having 0% support complaints — i.e. a perfectly healthy
support operation — and ranked the most painful accounts LAST.

A scoring engine that converts infrastructure failure into a positive signal is
worse than no engine. So: we prove reachability first, and we refuse to record
a zero we cannot distinguish from a failure.

Usage:
    python -m src.collect_playstore            # all prospects
    python -m src.collect_playstore --id groww # single prospect
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "out"

# A package we are confident exists and has reviews. Used purely as a
# canary to distinguish "network is blocked" from "this app has no reviews".
CANARY_PACKAGE = "com.whatsapp"

REVIEW_COUNT = 300          # per app, newest-first
REVIEW_LANG = "en"
REVIEW_COUNTRY = "in"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def verify_reachable() -> tuple[bool, str]:
    """
    Prove we can actually reach the Play Store before trusting any result.

    Returns (reachable, reason). We deliberately use app() rather than
    reviews() because app() raises on failure instead of silently returning [].
    """
    try:
        from google_play_scraper import app
    except ImportError:
        return False, "google-play-scraper not installed (pip install google-play-scraper)"

    try:
        meta = app(CANARY_PACKAGE, lang=REVIEW_LANG, country=REVIEW_COUNTRY)
    except Exception as exc:  # noqa: BLE001 - we want every failure mode
        return False, f"canary fetch failed: {type(exc).__name__}: {exc}"

    if not meta or meta.get("reviews") in (None, 0):
        return False, "canary returned no data - source reachable but responding emptily"

    return True, "canary OK"


def fetch_app_meta(package: str) -> dict:
    from google_play_scraper import app

    meta = app(package, lang=REVIEW_LANG, country=REVIEW_COUNTRY)
    return {
        "rating": meta.get("score"),
        "ratings_count": meta.get("ratings"),
        "reviews_count": meta.get("reviews"),
        "installs": meta.get("installs"),
        "updated": meta.get("updated"),
    }


def fetch_reviews(package: str) -> list[dict]:
    from google_play_scraper import Sort, reviews

    result, _ = reviews(
        package,
        lang=REVIEW_LANG,
        country=REVIEW_COUNTRY,
        sort=Sort.NEWEST,
        count=REVIEW_COUNT,
    )
    return [
        {
            "score": r.get("score"),
            "content": r.get("content") or "",
            "at": r.get("at").isoformat() if r.get("at") else None,
            "thumbs_up": r.get("thumbsUpCount"),
        }
        for r in result
    ]


def collect_one(prospect: dict, reachable: bool, reason: str) -> dict:
    """
    Collect signals for one prospect.

    Returns a record where EVERY field is either a real collected value or
    None with an explicit `status` explaining why. Never a fabricated default.
    """
    pid = prospect["id"]
    package = prospect.get("android_package")

    record: dict = {
        "prospect_id": pid,
        "name": prospect["name"],
        "collected_at": _now(),
        "source": "play_store",
        "package": package,
        "status": None,
        "status_reason": None,
        "app_meta": None,
        "reviews": None,
        "review_count_collected": 0,
    }

    if not package:
        record["status"] = "not_applicable"
        record["status_reason"] = "prospect has no Android app (web-primary product)"
        return record

    if not reachable:
        record["status"] = "unreachable"
        record["status_reason"] = reason
        return record

    try:
        record["app_meta"] = fetch_app_meta(package)
    except Exception as exc:  # noqa: BLE001
        record["status"] = "error"
        record["status_reason"] = f"app meta: {type(exc).__name__}: {exc}"
        return record

    try:
        revs = fetch_reviews(package)
    except Exception as exc:  # noqa: BLE001
        record["status"] = "error"
        record["status_reason"] = f"reviews: {type(exc).__name__}: {exc}"
        return record

    # The critical guard. Reachability was verified against the canary, but
    # verify again per-app: a zero here, with app_meta showing a large review
    # count, means the review endpoint failed silently for THIS package.
    declared = (record["app_meta"] or {}).get("reviews") or 0
    if not revs and declared > 0:
        record["status"] = "suspect_empty"
        record["status_reason"] = (
            f"review fetch returned 0 but app metadata declares {declared:,} reviews - "
            "treating as collection failure, not as zero complaints"
        )
        return record

    record["reviews"] = revs
    record["review_count_collected"] = len(revs)
    record["status"] = "ok"
    record["status_reason"] = f"collected {len(revs)} reviews"
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect Play Store signals")
    parser.add_argument("--id", help="collect a single prospect by id")
    parser.add_argument(
        "--out",
        default=str(OUT / "signals_playstore.json"),
        help="output path",
    )
    args = parser.parse_args()

    prospects = yaml.safe_load((DATA / "prospects.yaml").read_text())["prospects"]
    if args.id:
        prospects = [p for p in prospects if p["id"] == args.id]
        if not prospects:
            print(f"No prospect with id {args.id!r}", file=sys.stderr)
            return 1

    reachable, reason = verify_reachable()
    print(f"[reachability] {'OK' if reachable else 'BLOCKED'} - {reason}")
    if not reachable:
        print(
            "[reachability] Proceeding, but every record will be marked "
            "'unreachable'. No zeros will be recorded as real values.",
            file=sys.stderr,
        )

    records = []
    for p in prospects:
        rec = collect_one(p, reachable, reason)
        records.append(rec)
        print(f"  {rec['prospect_id']:<16} {rec['status']:<16} {rec['status_reason']}")

    OUT.mkdir(exist_ok=True)
    payload = {
        "collected_at": _now(),
        "source_reachable": reachable,
        "reachability_reason": reason,
        "records": records,
    }
    Path(args.out).write_text(json.dumps(payload, indent=2))

    ok = sum(1 for r in records if r["status"] == "ok")
    print(f"\n{ok}/{len(records)} prospects collected successfully -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
