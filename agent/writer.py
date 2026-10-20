"""Writer: drafts one message for one prospect in one angle."""

from __future__ import annotations

from agent.angles import ANGLES, HOUSE_RULES
from agent.brief import brief_as_prompt
from agent.llm import LLM

SYSTEM = """You write cold outreach for an enterprise conversational-AI company \
selling into Indian BFSI (banking, financial services, insurance), fintech and \
insurtech. Your recipients are senior operators: heads of customer experience, \
support operations, digital. They receive dozens of vendor emails a week and \
delete almost all of them unread.

You are not a marketer. You write like someone who has actually worked a support \
queue and has done a piece of homework on this specific company.

THE RULE THAT OVERRIDES EVERYTHING ELSE:
You may only state facts that appear in the RESEARCH BRIEF you are given. You \
know nothing else about this company. Do not use anything you may have learned \
elsewhere about their funding, size, market position, leadership, product \
roadmap or recent news. If a fact is not in the brief, it does not exist.

The recipient is the one person guaranteed to notice an invented detail about \
their own company, and a single wrong fact ends the conversation permanently. \
When in doubt, say less."""

TEMPLATE = """{brief}

---
ANGLE: {angle_name}
THESIS: {thesis}
HOW TO EXECUTE IT: {guidance}
KNOWN RISK WITH THIS ANGLE: {risk}
{house_rules}
{revision_block}
Write the email. Output exactly this shape and nothing else:

SUBJECT: <subject line, under 60 characters, lower-case after the first word, \
no company name stuffing>

<body>
"""

REVISION = """
---
YOUR PREVIOUS DRAFT WAS REJECTED BY REVIEW.

Previous draft:
{previous}

Reviewer verdict: {verdict}
Specific failures to fix:
{failures}

Rewrite it. Fix every failure listed. Do not simply reword; if the reviewer said \
the opening is generic, the opening must now lead with something different, not \
the same opening with adjectives changed.
"""


def draft(
    llm: LLM,
    brief: dict,
    angle_key: str,
    previous: str | None = None,
    verdict: str | None = None,
    failures: list[str] | None = None,
) -> str:
    angle = ANGLES[angle_key]
    revision_block = ""
    if previous:
        revision_block = REVISION.format(
            previous=previous,
            verdict=verdict or "rejected",
            failures="\n".join(f"- {f}" for f in (failures or [])),
        )

    user = TEMPLATE.format(
        brief=brief_as_prompt(brief),
        angle_name=angle["name"],
        thesis=angle["thesis"],
        guidance=angle["guidance"],
        risk=angle["risk"],
        house_rules=HOUSE_RULES,
        revision_block=revision_block,
    )
    return llm.complete(
        f"write:{angle_key}", SYSTEM, user, max_tokens=6000
    ).strip()
