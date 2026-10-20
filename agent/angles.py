"""
Outreach angles — the experiment arms.

Each angle is a genuinely different strategy for opening a cold conversation
with a senior BFSI operator, not a tone variation. "Formal vs friendly" is not
an experiment; it produces the same message twice. These differ in what they
LEAD WITH and what they ask for, which is what actually moves reply rate.

The engine runs several arms per prospect, scores each, and logs the result.
Over runs, experiments.py aggregates which arm wins for which prospect profile.
That loop is the difference between a message generator and a growth engine.
"""

from __future__ import annotations

ANGLES = {
    "evidence_audit": {
        "name": "Evidence audit",
        "thesis": "Lead with the measured number about their own operation.",
        "guidance": (
            "Open with the single most specific measured fact about THEIR support "
            "surface. State it plainly, say where it came from so they can check it "
            "in ten minutes, and ask whether it matches their internal picture. "
            "No pitch, no product mention, no meeting request."
        ),
        "risk": "Can read as an audit nobody asked for. Tone must be curious, not accusatory.",
    },
    "contrarian_metric": {
        "name": "Contrarian metric",
        "thesis": "Challenge the metric they are almost certainly reporting on.",
        "guidance": (
            "Argue that deflection rate is the wrong number, using our own eval "
            "result as evidence: two systems with near-identical deflection and "
            "wildly different correctness. Make the argument about their reporting, "
            "not about their vendor. Ask what they currently measure instead."
        ),
        "risk": "Can feel like a lecture. Must concede what deflection rate IS good for.",
    },
    "single_quote": {
        "name": "One customer's words",
        "thesis": "Open with one real complaint, nothing else.",
        "guidance": (
            "Open with a single verbatim customer quote from their own public "
            "reviews, then one sentence on what makes that CLASS of complaint "
            "different from product complaints. Shortest possible message. The "
            "quote does the work; do not explain it twice."
        ),
        "risk": "Can feel like an attack. Frame as 'this is the category, not a gotcha'.",
    },
    "peer_benchmark": {
        "name": "Peer position",
        "thesis": "Tell them where they sit in a measured set.",
        "guidance": (
            "Lead with their rank in the measured cohort without naming other "
            "companies. Be precise about what was measured and what was not. The "
            "value is the comparison existing at all, since nobody publishes this. "
            "Offer the methodology, not a meeting."
        ),
        "risk": "Meaningless if the cohort is not described honestly. Name the sample size.",
    },
    "question_first": {
        "name": "Question first",
        "thesis": "Make no claim at all. Ask one real question.",
        "guidance": (
            "Open with a genuine operational question that only someone who has "
            "worked a support queue would think to ask, about how a specific hard "
            "query class is routed at their company. Mention the data you have only "
            "in one closing line, as an offer. The question must be one they would "
            "find interesting to answer even if they never reply."
        ),
        "risk": "Can look like it wants free consulting. Must offer something back.",
    },
}

# Structural rules every angle inherits. These encode what actually gets read
# by someone senior: brevity, one idea, something checkable, no manufactured
# urgency, and no request for time in a first touch.
HOUSE_RULES = """
HARD CONSTRAINTS on every message:
- Under 130 words. A senior operator reads two lines before deciding.
- Exactly one idea. If you are making two points, cut the weaker one.
- Every specific claim must be checkable by the recipient within ten minutes.
- No meeting request, no calendar link, no "quick call?" in a first touch.
- No manufactured urgency, no flattery, no "I've been following your journey".
- No em-dashes. No "not just X, but Y". No rhetorical questions used as filler.
- Name the limitation of your own data in the message where it matters. A claim
  with its caveat attached is more credible than one without, to this audience.
- Plain British-neutral business English. Write like a practitioner, not a
  marketer. If a sentence sounds like it came from a sales sequence, cut it.
- Sign-off placeholder is exactly {sender}. Greeting uses {first_name}.
"""
