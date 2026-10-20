"""
Critic: scores a draft and decides whether it ships.

This is what makes the thing an agent rather than a prompt with extra steps.
The writer produces; the critic judges against a rubric it cannot see the
writer's reasoning for, and sends work back with specific failures. The loop
runs until the draft passes or the round budget is spent.

TWO KINDS OF JUDGEMENT, DELIBERATELY SEPARATED
-----------------------------------------------
HARD FAILS are factual and structural. They are not matters of taste and a
draft that trips one cannot ship at any score. The most important is
unsupported_claim: any specific assertion about the company that is not in the
brief. That is the guard against the single failure mode that would actually
damage the sender - a fluent invented fact about the recipient's own business.

SCORED DIMENSIONS are quality judgements, 1-5. They decide which of several
angles wins, not whether a message is safe to send.

The critic runs at effort "high". Note the honest limitation: this SDK version
removed temperature, so the critic is NOT deterministic - two reviews of the
same draft can differ. Scores are therefore a judgement, not a measurement, and
should not be quoted to two decimal places as if they were repeatable.
"""

from __future__ import annotations

import json

from agent.brief import brief_as_prompt
from agent.llm import LLM

PASS_THRESHOLD = 3.6   # mean of scored dimensions
HARD_FAIL_KEYS = [
    "unsupported_claim",
    "generic_opening",
    "asks_for_meeting",
    "over_length",
    "manufactured_urgency",
    "caveat_stripped",
    "derived_figure",
    "nothing_offered",
]

SYSTEM = """You review cold outreach emails before they are sent to senior \
operators at Indian BFSI, fintech and insurtech companies. You are the last \
check before a real email reaches a real person.

You are a hostile reader. Assume the recipient deletes 99% of what arrives and \
is actively looking for a reason to delete this one. Your job is to find that \
reason before they do.

You are strict about facts above everything else. You have the research brief \
the writer was given. Any specific claim in the draft that is not supported by \
that brief is a hard fail, regardless of how plausible it sounds or how well the \
email otherwise reads. Plausible-and-unsupported is the worst case, not a \
borderline one, because it is the kind that gets sent.

Score honestly. A competent, inoffensive, forgettable email is a 2, not a 4. \
Most cold outreach deserves a 2."""

RUBRIC = """{brief}

---
DRAFT UNDER REVIEW (angle: {angle}):

{draft}

---
Review it.

HARD FAILS — each is true or false. Any true means the draft cannot ship:
- unsupported_claim: states a specific fact about this company (a number, an \
event, a product detail, a person, a market position) that does NOT appear in \
the brief above. Vague industry generalities are not claims; specifics are.
- generic_opening: the first sentence would work unchanged for any other \
company in this sector.
- asks_for_meeting: requests a call, a meeting, time, or includes a calendar \
link. This is a first touch and must not.
- over_length: body exceeds 130 words.
- manufactured_urgency: invents time pressure, scarcity, or a deadline.
- caveat_stripped: presents a measured figure as more conclusive than the brief \
supports, or omits a limitation that materially changes how the number reads.
- derived_figure: restates a number in a form the brief does not use (converting \
a percentage into a count, summing two figures, computing a rate). The \
arithmetic being correct does not matter: a derived figure cannot be checked \
against the brief, and in the first live run one shipped after being caught once.
- nothing_offered: gives the recipient nothing they keep whether or not they \
reply. A message that reports a statistic and asks a question, with no concrete \
offer of the methodology, the query set or the failure cases, is a stat report. \
This was the single most common failure in the first live run.

SCORED 1-5 (5 is rare):
- specificity: contains something true only of THIS company
- verifiability: recipient could check the central claim within ten minutes
- insight: tells them something about their own operation they likely had not \
framed this way
- brevity: every sentence earns its place
- voice: reads as a practitioner, not a sales sequence

Return ONLY this JSON:
{{
  "hard_fails": {{"unsupported_claim": false, "generic_opening": false, \
"asks_for_meeting": false, "over_length": false, "manufactured_urgency": false, \
"caveat_stripped": false, "derived_figure": false, "nothing_offered": false}},
  "unsupported_claims_found": ["quote the exact phrase, one per entry"],
  "scores": {{"specificity": 0, "verifiability": 0, "insight": 0, "brevity": 0, \
"voice": 0}},
  "verdict": "one sentence, blunt",
  "failures": ["specific, actionable fix, one per entry"],
  "strongest_line": "the one line worth keeping"
}}"""


def review(llm: LLM, brief: dict, angle_key: str, draft_text: str) -> dict:
    user = RUBRIC.format(
        brief=brief_as_prompt(brief), angle=angle_key, draft=draft_text
    )
    result = llm.json_complete(
        f"critique:{angle_key}", SYSTEM, user, max_tokens=5000
    )

    hf = result.get("hard_fails", {}) or {}
    tripped = [k for k in HARD_FAIL_KEYS if hf.get(k) is True]
    scores = result.get("scores", {}) or {}
    vals = [v for v in scores.values() if isinstance(v, (int, float))]
    mean = round(sum(vals) / len(vals), 2) if vals else 0.0

    result["hard_fails_tripped"] = tripped
    result["mean_score"] = mean
    result["passed"] = (not tripped) and mean >= PASS_THRESHOLD
    return result
