"""
Scoring engine.

PRIORITY = (icp_fit * w1 + pain_intensity * w2 + reachability * w3) * confidence

The confidence multiplier is the part worth defending. Most prospecting tools
treat a missing signal as an average one, which systematically promotes
prospects you know nothing about into the middle of the queue. This engine
treats a missing signal as missing: fewer collected signals -> lower multiplier
-> lower rank, and below a threshold the prospect is held out of the outreach
queue entirely rather than being contacted on thin evidence.

Every score carries a `why` trace. If a prospect asks how you reached a
conclusion about their operation, the answer is reproducible.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _norm(value: float | None, lo: float, hi: float) -> float | None:
    """Normalise to 0-100, clamped. None in -> None out."""
    if value is None:
        return None
    if hi == lo:
        return 0.0
    pct = (value - lo) / (hi - lo)
    return round(max(0.0, min(1.0, pct)) * 100, 2)


def score_icp(prospect: dict, cfg: dict) -> tuple[float, list[str]]:
    c = cfg["icp_fit"]
    why = []
    base = c["vertical_has_nugget_page"].get(
        prospect.get("vertical"), c["vertical_has_nugget_page"]["other"]
    )
    why.append(f"vertical '{prospect.get('vertical')}' has a published Nugget page: {base}")

    reg_bonus = sum(c["regulator_bonus"].get(r, 0) for r in prospect.get("regulator", []))
    reg_bonus = min(reg_bonus, c["regulator_bonus_cap"])
    if reg_bonus:
        why.append(
            f"regulated by {'/'.join(prospect['regulator'])} -> compliance posture is a "
            f"differentiator not overhead: +{reg_bonus}"
        )

    sub_bonus = c["sub_vertical_bonus"].get(prospect.get("sub_vertical"), 0)
    if sub_bonus:
        why.append(
            f"sub-vertical '{prospect['sub_vertical']}' carries the hard-query class "
            f"Nugget's Wealth page does not yet address: +{sub_bonus}"
        )

    total = min(100.0, base + reg_bonus + sub_bonus)
    return round(total, 2), why


def score_pain(summary: dict, cfg: dict) -> tuple[float | None, int, list[str]]:
    c = cfg["pain_intensity"]["inputs"]
    sig = summary["signals"]
    why = []
    weighted = 0.0
    weight_used = 0.0
    collected = 0

    pairs = [
        ("support_review_share", sig.get("support_review_share")),
        ("unresolved_language_share", sig.get("unresolved_language_share")),
        ("rating_trend", sig.get("rating_trend")),
        ("review_volume", sig.get("review_volume")),
    ]

    for key, raw in pairs:
        spec = c[key]
        if raw is None:
            why.append(f"{key}: NOT COLLECTED - excluded from score, confidence reduced")
            continue
        val = raw
        if spec.get("transform") == "log10":
            val = math.log10(max(val, 1))
            lo = math.log10(max(spec["scale"]["min"], 1))
            hi = math.log10(max(spec["scale"]["max"], 1))
        else:
            lo, hi = spec["scale"]["min"], spec["scale"]["max"]
        n = _norm(val, lo, hi)
        weighted += n * spec["weight"]
        weight_used += spec["weight"]
        collected += 1
        why.append(f"{key}={raw} -> normalised {n} (weight {spec['weight']})")

    if collected == 0:
        return None, 0, why + ["no pain signals collected - prospect cannot be scored"]

    # Renormalise over the weights actually used, so a missing input does not
    # silently drag the score toward zero. Missingness is handled by the
    # confidence multiplier instead - one mechanism, not two.
    score = weighted / weight_used
    why.append(f"renormalised over collected weight {weight_used:.2f} -> {score:.2f}")
    return round(score, 2), collected, why


def score_reach(prospect: dict, overrides: dict, cfg: dict) -> tuple[float | None, int, list[str]]:
    c = cfg["reachability"]["inputs"]
    o = overrides.get(prospect["id"])
    why = []
    if not o:
        return None, 0, ["no reachability assessment recorded - see data/reachability.yaml"]

    weighted = 0.0
    weight_used = 0.0
    collected = 0

    if o.get("leadership_publicly_active") is not None:
        v = 100.0 if o["leadership_publicly_active"] else 20.0
        weighted += v * c["leadership_publicly_active"]["weight"]
        weight_used += c["leadership_publicly_active"]["weight"]
        collected += 1
        why.append(f"named leader publicly active: {o['leadership_publicly_active']} -> {v}")

    if o.get("warm_path_exists") is not None:
        v = 100.0 if o["warm_path_exists"] else 25.0
        weighted += v * c["warm_path_exists"]["weight"]
        weight_used += c["warm_path_exists"]["weight"]
        collected += 1
        why.append(f"warm path: {o.get('warm_path_note', o['warm_path_exists'])} -> {v}")

    band = o.get("company_size_band")
    if band:
        v = c["company_size_band"]["bands"].get(band, 50)
        weighted += v * c["company_size_band"]["weight"]
        weight_used += c["company_size_band"]["weight"]
        collected += 1
        why.append(f"size band '{band}' -> {v}")

    if collected == 0:
        return None, 0, why
    return round(weighted / weight_used, 2), collected, why


def _confidence_for_ratio(ratio: float, conf_map: dict) -> float:
    """
    Step function: take the multiplier for the highest threshold the ratio
    meets or exceeds. Floors rather than interpolates - we would rather
    understate confidence than overstate it.
    """
    best = 0.0
    for threshold in sorted(float(k) for k in conf_map):
        if ratio >= threshold:
            best = float(conf_map[threshold])
    return round(best, 3)


def run(cfg: dict, prospects: list[dict], classified: dict, overrides: dict) -> list[dict]:
    w = cfg["weights"]
    conf_map = cfg["confidence"]["ratio_multiplier"]
    min_conf = cfg["confidence"]["min_confidence_to_contact"]
    by_id = {s["prospect_id"]: s for s in classified["summaries"]}

    rows = []
    for p in prospects:
        summary = by_id.get(p["id"], {"signals": {}, "hard_query_counts": {}, "evidence": [],
                                      "collector_reason": "no collector record"})
        icp, icp_why = score_icp(p, cfg)
        pain, pain_n, pain_why = score_pain(summary, cfg)
        reach, reach_n, reach_why = score_reach(p, overrides, cfg)

        # Count reachability SUB-signals individually. Counting the whole
        # factor as one point let a single pre-filled field (company_size_band)
        # stand in for a full reachability assessment, producing confidence
        # 1.00 across a universe where two of the three fields were null.
        total_signals = pain_n + reach_n
        ratio = total_signals / cfg["confidence"]["total_possible_signals"]
        confidence = _confidence_for_ratio(ratio, conf_map)

        # ICP is always available; pain and reach may not be. Renormalise the
        # top-level weights over the factors we actually have.
        parts = [(icp, w["icp_fit"])]
        if pain is not None:
            parts.append((pain, w["pain_intensity"]))
        if reach is not None:
            parts.append((reach, w["reachability"]))
        wsum = sum(x[1] for x in parts)
        raw = sum(v * ww for v, ww in parts) / wsum

        priority = round(raw * confidence, 2)
        contactable = confidence >= min_conf and pain is not None

        rows.append(
            {
                "prospect_id": p["id"],
                "name": p["name"],
                "vertical": p.get("vertical"),
                "sub_vertical": p.get("sub_vertical"),
                "icp_fit": icp,
                "pain_intensity": pain,
                "reachability": reach,
                "raw_score": round(raw, 2),
                "signals_collected": total_signals,
                "confidence": confidence,
                "priority": priority,
                "contactable": contactable,
                "hold_reason": None
                if contactable
                else (
                    f"confidence {confidence:.2f} below threshold {min_conf} "
                    f"({total_signals} signals collected) - not enough evidence to "
                    "justify a personalised claim about this company"
                ),
                "hard_query_counts": summary.get("hard_query_counts", {}),
                "evidence": summary.get("evidence", []),
                "why": {"icp_fit": icp_why, "pain_intensity": pain_why, "reachability": reach_why},
            }
        )

    rows.sort(key=lambda r: r["priority"], reverse=True)
    return rows


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "out" / "pipeline.json"))
    args = ap.parse_args()

    cfg = yaml.safe_load((ROOT / "data" / "scoring.yaml").read_text())
    prospects = yaml.safe_load((ROOT / "data" / "prospects.yaml").read_text())["prospects"]
    classified = json.loads((ROOT / "out" / "signals_classified.json").read_text())

    ov_path = ROOT / "data" / "reachability.yaml"
    overrides = yaml.safe_load(ov_path.read_text())["prospects"] if ov_path.exists() else {}

    rows = run(cfg, prospects, classified, overrides)

    payload = {
        "generated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
        "synthetic": classified.get("synthetic", False),
        "source_reachable": classified.get("source_reachable"),
        "pipeline": rows,
    }
    Path(args.out).write_text(json.dumps(payload, indent=2))

    flag = "  [SYNTHETIC DATA]" if payload["synthetic"] else ""
    print(f"\nRANKED PIPELINE{flag}\n" + "=" * 84)
    print(f"{'#':<3}{'PROSPECT':<20}{'ICP':>6}{'PAIN':>7}{'REACH':>7}{'CONF':>7}{'PRIORITY':>10}  STATUS")
    print("-" * 84)
    for i, r in enumerate(rows[:15], 1):
        pain = f"{r['pain_intensity']:.0f}" if r["pain_intensity"] is not None else "--"
        reach = f"{r['reachability']:.0f}" if r["reachability"] is not None else "--"
        status = "contact" if r["contactable"] else "HOLD"
        print(
            f"{i:<3}{r['name'][:19]:<20}{r['icp_fit']:>6.0f}{pain:>7}{reach:>7}"
            f"{r['confidence']:>7.2f}{r['priority']:>10.2f}  {status}"
        )
    held = sum(1 for r in rows if not r["contactable"])
    print("-" * 84)
    print(f"{len(rows)-held} contactable, {held} held back for insufficient evidence")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
