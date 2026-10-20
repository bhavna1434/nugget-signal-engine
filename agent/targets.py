"""
Target layer: who the message is addressed to.

Loads data/targets.yaml and renders the recipient into the research brief under
the same closed-world rule that governs company facts — the writer may state
nothing about the person that is not recorded here, with a source.

THE FAILURE THIS PREVENTS
Ask any model to write a personal note to "the Head of Customer Experience at
PolicyBazaar" and it will produce something warm about their career, their
recent thinking, and the priorities they must be weighing this quarter. All of
it invented, all of it fluent, and the recipient is the one person on earth who
knows it is invented. A role without a person is an invitation to hallucinate a
person, so the brief states the mode explicitly and tells the writer what it is
therefore not allowed to do.

THREE MODES
  named   a verified person. The writer may reference their recorded public
          statements, each of which carries a URL the recipient could check.
  role    the function, not the human. The writer addresses the role's
          concerns and must not imply any knowledge of the individual.
  unknown nothing recorded. Company-level only.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TARGETS = ROOT / "data" / "targets.yaml"


def load_targets() -> dict:
    if not TARGETS.exists():
        return {}
    return (yaml.safe_load(TARGETS.read_text()) or {}).get("targets", {}) or {}


def get_target(prospect_id: str) -> dict:
    t = load_targets().get(prospect_id)
    if not t:
        return {"mode": "unknown"}

    mode = t.get("mode", "unknown")
    if mode == "named":
        # A named target with no sourced facts is a name and nothing else.
        # Keep it named — the greeting is still real — but the writer gets no
        # material about them, which is correct.
        facts = [f for f in (t.get("facts") or []) if f.get("claim") and f.get("source")]
        dropped = len(t.get("facts") or []) - len(facts)
        return {
            "mode": "named",
            "first_name": t.get("first_name") or "",
            "full_name": t.get("full_name") or "",
            "role": t.get("role") or "",
            "facts": facts,
            "facts_dropped_unsourced": dropped,
            "verified_on": t.get("verified_on"),
        }
    if mode == "role":
        return {
            "mode": "role",
            "role": t.get("role") or "",
            "rationale": (t.get("rationale") or "").strip(),
        }
    return {"mode": "unknown"}


def target_block(t: dict) -> str:
    """How the recipient appears in the writer's prompt."""
    if t["mode"] == "named":
        lines = [
            "RECIPIENT: a specific, verified person.",
            f"  Name: {t['full_name'] or t['first_name']}",
            f"  Role: {t['role']}",
        ]
        if t.get("verified_on"):
            lines.append(f"  Role last confirmed: {t['verified_on']}")
        if t["facts"]:
            lines.append("  Publicly on record (each checkable at the URL given):")
            for f in t["facts"]:
                lines.append(f"    - {f['claim']}  [{f['source']}]")
            lines.append(
                "  You may reference these. You may reference NOTHING ELSE about "
                "this person: not their career history, not their priorities, not "
                "opinions they have not published here."
            )
        else:
            lines.append(
                "  Nothing is on record about this person beyond name and role. "
                "Use the name in the greeting and write to the role. Do not imply "
                "you know anything about them."
            )
        if t.get("facts_dropped_unsourced"):
            lines.append(
                f"  ({t['facts_dropped_unsourced']} unsourced claim(s) were "
                "dropped from this record and are not available to you.)"
            )
        return "\n".join(lines)

    if t["mode"] == "role":
        s = [
            "RECIPIENT: a ROLE, not an identified person.",
            f"  Role: {t['role']}",
        ]
        if t.get("rationale"):
            s.append(f"  Why this role owns the problem: {t['rationale']}")
        s.append(
            "  You do not know who holds this role. Write to the concerns of the "
            "role. Do NOT invent a name, a history, a recent talk, a quote or a "
            "priority. Do not write anything that implies you know this person. "
            "The greeting placeholder stays {first_name} for a human to fill."
        )
        return "\n".join(s)

    return (
        "RECIPIENT: not identified.\n"
        "  No person or role is recorded for this company. Keep the message "
        "company-level. Do not address an individual or imply you know who "
        "handles this."
    )


def target_label(t: dict) -> str:
    """Short label for logs and the console."""
    if t["mode"] == "named":
        n = t["full_name"] or t["first_name"] or "named"
        return f"{n} — {t['role']}" if t["role"] else n
    if t["mode"] == "role":
        return f"{t['role']} (role only)"
    return "unidentified"
