"""
Outreach formats — the second experiment dimension.

Angles are WHAT you lead with. Formats are HOW it arrives. They are
independent: the same evidence-audit angle reads differently as a cold email,
a LinkedIn note, a card on someone's desk or a ninety-second screen recording,
and there is no reason to assume the angle that wins over email also wins in
the post.

Treating format as its own dimension is what makes "which format moves senior
leaders" a measured question rather than an assertion. The experiment log
records format x angle, so the aggregate answers both.

WHY A PHYSICAL FORMAT IS IN HERE AND NOT AS A GIMMICK
A senior operator at a large BFSI firm receives dozens of vendor emails a week
and deletes nearly all of them unread. The same person receives almost no post.
A card carrying their OWN public complaint data is specific, checkable, costs
about the price of a coffee, cannot be deleted in one keystroke, and creates a
legitimate reason for the digital follow-up a week later. That is the whole
argument: not novelty, but a channel where the competition is absent and the
evidence still does the work.

Each format declares its own constraints, because the same message cannot
simply be reflowed: a card has no room for caveats in prose, so the caveat has
to become a line of small print; a video script is spoken, so it cannot lean on
a table.
"""

from __future__ import annotations

FORMATS = {
    "email": {
        "name": "Cold email",
        "channel": "digital",
        "cost": "free",
        "constraints": (
            "Under 130 words in the body. A subject line under 60 characters. "
            "No meeting request. Every caveat stated inline, in the sentence "
            "that needs it."
        ),
        "shape": "SUBJECT: <subject>\n\n<body>",
        "why": "The default. Cheap, instant, and the most competitive inbox they have.",
    },
    "linkedin": {
        "name": "LinkedIn note",
        "channel": "digital",
        "cost": "free",
        "constraints": (
            "Under 70 words. No subject line. More conversational than an email "
            "and it must not read as an email pasted into a message box. One "
            "question, no attachment, no link unless it is the only payload."
        ),
        "shape": "<message>",
        "why": "Shorter leash than email: a wall of text here is ignored faster.",
    },
    "signal_card": {
        "name": "Printed signal card",
        "channel": "phygital",
        "cost": "about 40 rupees plus postage",
        "constraints": (
            "A physical A6 card posted to their office. FRONT: one number and "
            "one line, nothing else - it has to work when glanced at on a desk. "
            "BACK: the verbatim customer quote, two lines of context, the "
            "limitation in small print, and a short URL plus the sender's name. "
            "No logo, no envelope branding, nothing that reads as marketing "
            "collateral. Total under 70 words across both faces."
        ),
        "shape": (
            "FRONT_STAT: <the single number>\n"
            "FRONT_LINE: <one line, under 12 words>\n"
            "BACK_QUOTE: <verbatim customer review, trimmed>\n"
            "BACK_BODY: <two lines of context>\n"
            "BACK_SMALLPRINT: <the limitation, one line>"
        ),
        "why": (
            "The channel where the competition is absent. Specific, tactile, and "
            "it earns the follow-up email a week later."
        ),
    },
    "micropage": {
        "name": "Personal micro-page",
        "channel": "digital",
        "cost": "free",
        "constraints": (
            "A single page built for one recipient. A headline naming their "
            "company, the three measured figures, two verbatim quotes, the "
            "limitations stated plainly, and one question. Under 160 words of "
            "prose. It must be readable in forty seconds and must not ask for "
            "anything."
        ),
        "shape": (
            "HEADLINE: <under 10 words>\n"
            "STANDFIRST: <one sentence>\n"
            "BODY: <the figures and what they mean>\n"
            "LIMITS: <what this does not establish>\n"
            "QUESTION: <the one question>"
        ),
        "why": (
            "Gives the email somewhere to point, and the visit itself is a signal "
            "that the subject landed."
        ),
    },
    "video_script": {
        "name": "90-second screen walkthrough",
        "channel": "creative",
        "cost": "free",
        "constraints": (
            "A script to be read aloud over a screen recording of their own "
            "data. Written for the ear: short sentences, no sub-clauses, no "
            "figures the listener cannot hold in their head. Mark what is on "
            "screen at each beat. 150 to 190 words, which is about ninety "
            "seconds spoken. It ends on a question, not an ask."
        ),
        "shape": (
            "[0:00 ON SCREEN: <what is visible>]\n<spoken line>\n\n"
            "[0:20 ON SCREEN: <what is visible>]\n<spoken line>\n..."
        ),
        "why": (
            "A voice reading someone their own numbers is harder to dismiss than "
            "text, and it proves a human did the work."
        ),
    },
}

# Formats whose output is rendered rather than sent as prose. The card goes to
# a printer; the micro-page becomes HTML.
RENDERED = {"signal_card", "micropage"}


def format_block(key: str) -> str:
    """The format's instructions, as they appear in the writer's prompt."""
    f = FORMATS[key]
    return (
        f"FORMAT: {f['name']} ({f['channel']})\n"
        f"WHY THIS FORMAT: {f['why']}\n"
        f"CONSTRAINTS: {f['constraints']}\n\n"
        f"Output exactly this shape and nothing else:\n{f['shape']}"
    )
