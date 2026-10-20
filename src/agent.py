"""
Two support agents over the same knowledge base.

BaselineAgent  - retrieval + always answer. The default behaviour of a support
                 bot built to maximise deflection rate.
RoutedAgent    - classify handling class FIRST, then answer / request data /
                 escalate. Optimises for correct disposition, not deflection.

The point of shipping both is that the DELTA is the argument. A deflection-rate
chart makes the baseline look better. A disposition-correctness chart shows the
baseline is confidently wrong on the most expensive query class in the book.

No API key, no network. Deterministic across runs so an eval result is
reproducible and a demo cannot fail on connectivity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

# Small FAQ knowledge base - representative of what a platform actually
# publishes. Note what is NOT here: anything about TDS reconciliation,
# settlement timing, or XIRR decomposition. That absence is the finding.
KB = [
    ("lock-in period",
     "The lock-in period is specified in the instrument's offer document. "
     "Please refer to the product page for the applicable tenure."),
    ("holding statement download",
     "You can download your holding statement from Portfolio > Statements."),
    ("kyc documents",
     "For KYC you need PAN, Aadhaar-linked mobile, and a bank proof."),
    ("minimum investment",
     "The minimum investment amount is listed on each product page."),
    ("tds",
     "TDS is deducted as applicable under the Income Tax Act. "
     "Please refer to your TDS certificate."),
    ("form 15g",
     "Form 15G can be submitted from Profile > Tax to apply for nil TDS."),
    ("maturity",
     "Maturity proceeds are credited to your registered bank account on maturity."),
    ("xirr returns",
     "XIRR is an annualised return metric and may differ from the coupon rate."),
    ("interest credited",
     "Interest is calculated and credited as per the terms of the instrument."),
    ("form 26as",
     "TDS credits reflect in Form 26AS. Please check after some time."),
    ("ckyc",
     "If KYC is rejected, please re-upload your documents."),
    ("complaint sebi",
     "For any grievance, please write to our support email."),
]

# Signals that a query depends on the individual user's own position.
PERSONAL = re.compile(
    r"\b(my|mine|i |i'?ve|me\b)|\blast (?:quarter|month)\b|\bhas my\b", re.I
)
# Signals that a query asks for advice / a recommendation.
ADVICE = re.compile(
    r"\bshould i\b|\bis (?:this|it) (?:safe|good|better)\b|\bwhich is better\b"
    r"|\brecommend\b|\badvice\b|\binvest more\b",
    re.I,
)
# Signals of a regulatory / grievance escalation.
GRIEVANCE = re.compile(r"\bsebi\b|\brbi\b|\birdai\b|\bombudsman\b|\bfile a complaint\b", re.I)

# The trap set: queries whose surface form matches a KB entry but whose correct
# resolution requires diagnosis against the user's record. Detected by the
# presence of a CONTRADICTION or DISCREPANCY, not by topic.
DISCREPANCY = re.compile(
    r"\bbut\b|\bstill\b|\bnot match|\bdoes not match|\bdoesn'?t match\b"
    r"|\bless than\b|\bmore than i\b|\bnot showing\b|\bnot received\b"
    r"|\bwhy (?:have|has|is|was|did)\b|\bnot reflect",
    re.I,
)


@dataclass
class Response:
    disposition: str           # answered | requested_data | escalated
    text: str
    confidence: float
    matched_kb: str | None = None
    reasoning: list[str] = field(default_factory=list)


def _retrieve(query: str) -> tuple[str | None, str | None, float]:
    """Crude bag-of-words retrieval. Deliberately simple - this is what a
    thin RAG layer over an FAQ actually behaves like."""
    q = set(re.findall(r"[a-z0-9]+", query.lower()))
    best, best_score, best_key = None, 0.0, None
    for key, answer in KB:
        k = set(re.findall(r"[a-z0-9]+", key.lower()))
        overlap = len(q & k) / max(len(k), 1)
        if overlap > best_score:
            best, best_score, best_key = answer, overlap, key
    if best_score < 0.34:
        return None, None, 0.0
    return best, best_key, round(min(0.95, 0.55 + best_score * 0.4), 2)


class BaselineAgent:
    """Retrieval + always answer. Escalates only when retrieval finds nothing."""

    name = "baseline_retrieval"

    def handle(self, query: str) -> Response:
        answer, key, conf = _retrieve(query)
        if answer is None:
            return Response(
                "escalated",
                "I'm not sure about that. Connecting you to an agent.",
                0.2,
                None,
                ["no KB match above threshold"],
            )
        return Response(
            "answered", answer, conf, key, [f"KB match '{key}' at confidence {conf}"]
        )


class RoutedAgent:
    """
    Classify disposition BEFORE retrieving.

    Order matters and is the whole design:
      1. grievance   -> escalate (regulatory logging requirement)
      2. advice      -> escalate (regulated activity)
      3. discrepancy -> escalate/diagnose (the trap class)
      4. personal    -> request authenticated data
      5. otherwise   -> retrieve and answer

    Rule 3 runs BEFORE retrieval. That single ordering decision is what stops
    the agent answering 'I submitted 15G but TDS was still deducted' with the
    generic 15G FAQ entry.
    """

    name = "routed"

    def handle(self, query: str) -> Response:
        why = []

        if GRIEVANCE.search(query):
            why.append("grievance/regulator reference detected")
            return Response(
                "escalated",
                "I'm routing this to a human agent and logging it in our "
                "grievance register so it is tracked formally.",
                0.9,
                None,
                why,
            )

        if ADVICE.search(query):
            why.append("advice-seeking language detected -> regulated activity")
            return Response(
                "escalated",
                "That's a suitability question I'm not able to advise on. "
                "Let me connect you with a licensed member of the team.",
                0.9,
                None,
                why,
            )

        if DISCREPANCY.search(query):
            why.append(
                "discrepancy language detected -> user reports a CONTRADICTION "
                "between expectation and outcome; requires diagnosis against "
                "their record, not a general-rule restatement"
            )
            return Response(
                "escalated",
                "I can see there's a mismatch between what you expected and "
                "what happened. That needs me to check your specific record "
                "rather than give you the general rule - routing to an agent "
                "with your case details attached.",
                0.85,
                None,
                why,
            )

        if PERSONAL.search(query):
            why.append("first-person/position-dependent query -> needs authenticated data")
            return Response(
                "requested_data",
                "Let me pull that from your account - one moment.",
                0.88,
                None,
                why,
            )

        answer, key, conf = _retrieve(query)
        if answer is None:
            why.append("no KB match")
            return Response("escalated", "Connecting you to an agent.", 0.3, None, why)
        why.append(f"impersonal factual query, KB match '{key}'")
        return Response("answered", answer, conf, key, why)


class IntegratedAgent(RoutedAgent):
    """
    RoutedAgent + authenticated access to the user's ledger.

    This models what Nugget's live API integration actually buys. The routing
    discipline is identical; the difference is that position-dependent queries
    become answerable instead of escalated, and trap queries become DIAGNOSABLE
    rather than merely escalated.

    This is the commercially important agent. The RoutedAgent alone automates
    very little, which is safe but is not a product. The argument is not
    'escalate more' - it is 'route correctly, then integrate so the correct
    route is usually an answer'.

    Trap handling here still does not assert a general rule. It answers from
    the user's actual record, which is the only answer that is both automated
    and correct.
    """

    name = "routed_integrated"

    # Which trap classes become resolvable with ledger access, and what the
    # agent would need to read to resolve them. This mapping is the
    # integration spec a solutions engineer would scope from.
    RESOLVABLE_WITH_LEDGER = {
        "15g": "declaration record (submitted_on, FY, assessee category) vs payout record date",
        "26as": "TDS challan filing status and deductor return cycle",
        "xirr": "user cash-flow ledger incl. TDS withheld and purchase price vs face value",
        "interest": "payout ledger line incl. gross, TDS, net, and day-count basis",
        "matur": "maturity date, record date, settlement cycle, payout rail status",
        "kyc": "verification failure reason code from the KYC provider",
    }

    def handle(self, query: str) -> Response:
        base = super().handle(query)

        # Advice and grievance stay escalated regardless of integration.
        # Data access does not make a suitability question answerable.
        if base.disposition == "escalated" and (
            ADVICE.search(query) or GRIEVANCE.search(query)
        ):
            return base

        q = query.lower()

        if base.disposition == "requested_data":
            return Response(
                "answered",
                "Reading your account now - here is the figure from your own ledger.",
                0.9,
                "ledger",
                base.reasoning + ["ledger integration available -> answered from user record"],
            )

        if base.disposition == "escalated":
            for key, needs in self.RESOLVABLE_WITH_LEDGER.items():
                if key in q:
                    return Response(
                        "answered",
                        f"Checking your record to reconcile this specifically "
                        f"(requires: {needs}).",
                        0.82,
                        "ledger_diagnosis",
                        base.reasoning
                        + [f"trap diagnosable with ledger access: {needs}"],
                    )

        return base


AGENTS = {a.name: a for a in (BaselineAgent(), RoutedAgent(), IntegratedAgent())}


def load_cases() -> list[dict]:
    return yaml.safe_load((ROOT / "evals" / "wealth_taxonomy.yaml").read_text())["cases"]
