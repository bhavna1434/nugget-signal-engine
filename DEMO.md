# Demo script — 5 minutes

Read this once tonight and once in the morning. Do not read it during.

Everything below is backed by a number in `out/` that you collected yourself.
Nothing in it is estimated, simulated or assumed.

---

## Before you walk in

```bash
cd ~/Documents/nugget-signal-engine && source .venv/bin/activate
python -m src.classify && python -m src.score && python -m src.run_evals && python -m src.generate_messages --top 5
```

Have open: the terminal, the dashboard, `evals/wealth_taxonomy.yaml`.

---

## The structure

You are not presenting a prospecting tool. You are presenting **an
investigation that disconfirmed its own hypothesis, and the engine that did
it.** That is a stronger thing to walk in with, and almost nobody does.

Lead with the disconfirmation. It is disarming, it is true, and it buys you
credibility for everything after it.

---

## The five minutes

**0:00 — Frame (30 sec)**

> "You're hiring someone to build an outbound engine, so I built one and
> pointed it at 5,700 real Play Store reviews across 19 BFSI apps. I want to
> start with the part that didn't work, because it's the more useful half."

**0:30 — The thesis that failed (90 sec)**

> "My hypothesis was that Indian fixed-income platforms are drowning in tax and
> settlement queries — TDS, Form 15G, maturity timing — that generic support
> bots answer confidently and wrongly. I do investor relations at a bond
> platform, so that's the query class I handle daily. I built the engine to
> find the prospects where it was most visible."

Then:

> "Zero TDS complaints in 5,700 reviews. Seventeen hard-query mentions total.
> And my first version of the counter was matching five-star reviews — Grip
> Invest praising their own repayment dashboard was being scored as repayment
> pain. The bond platforms I built the thesis around came out tenth and
> unscored, not first and second."

The honest conclusion, which is the line that matters:

> "Two readings fit and my data can't separate them. Either app reviews are the
> wrong instrument — nobody writes a Play Store review about Form 15G, they
> raise a ticket — or the class is rarer than I assumed. I think it's the
> first, but I can't prove it from this, so the hypothesis is untested rather
> than confirmed. SEBI SCORES categorises complaints by type and is where it
> would actually be visible. That's the next build."

**2:00 — What the data did support (60 sec)** — dashboard, pipeline section

> "What is measurable is the support-channel signal: among customers unhappy
> enough to write a paragraph, what share are unhappy about the channel rather
> than the product. That runs 0 to 7.6% across the set and it's checkable — any
> one of these companies can verify it on their own listing in ten minutes."

Point at the pipeline: smallcase, Upstox, INDmoney, PolicyBazaar, Razorpay.

> "14 contactable, 17 held back. Anything with fewer than 40 substantive
> reviews scores a dash, not a number. Navi returned 16 — a percentage off 16
> reviews is two reviews and a rounding error."

**3:00 — The eval (90 sec)** — the table that held

> "Separately, I built an eval harness over 18 real queries from this domain,
> and scored three agent configurations on whether they *disposed* of each
> query correctly rather than how many they deflected."

67% automated / 39% correct / 8 confidently wrong — versus 72% / 94% / 0.

> "Near-identical deflection. Two and a half times the accuracy. Eight
> compliance exposures versus zero. If a vendor reports deflection rate but not
> disposition correctness, that entire gap is invisible in your QBRs."

And the honest half:

> "Routing alone automates 11%, which is safe and commercially useless. The
> argument isn't 'escalate more' — it's route correctly, then integrate so the
> correct route is usually an answer. That second half is what your live
> integration actually sells."

**4:30 — Close (30 sec)**

> "Four bugs are documented in the README, including a confidence layer that
> reported perfect confidence in evidence that didn't exist and looked
> completely normal doing it. The engine's main value tonight was catching my
> own errors — three of the four were things I'd have shipped."

---

## The self-improvement loop (lead with this)

The engine reads its own critic's rejection log, finds the failure mode that is
dominant for one angle and not others, and rewrites that angle's instructions.
It proposes; a human applies; every change is versioned with the evidence that
motivated it.

Measured before and after, same prospects, same critic:

| angle | guidance | n | score | ship | rounds | top first-round failure |
|---|---|---|---|---|---|---|
| evidence_audit | original | 5 | 3.40 | 40% | 2.80 | derived_figure |
| evidence_audit | **evolved** | 2 | **3.60** | **100%** | 2.50 | **none** |
| single_quote | original | 5 | 3.48 | 60% | 2.80 | nothing_offered |
| single_quote | **evolved** | 2 | **3.30** | 50% | 2.00 | **unsupported_claim** |

**It helped one angle and hurt the other.** evidence_audit eliminated its target
failure and went to a 100% ship rate. single_quote traded one failure for a new
one: the rewrite's own example ("this kind of complaint usually points to a
handoff failing between X and Y") taught the writer to assert root causes the
brief could not support, and the critic caught it on the first draft.

**What to say:**

> "The loop rewrote two angles. One went to a 100% ship rate with its target
> failure eliminated. The other got worse, because the rewrite's own example
> taught the writer to assert things it couldn't support. Self-improvement
> shifts failure modes as much as it removes them. That's why the reviewer
> stays independent of the thing being improved, and why the loop proposes
> rather than auto-applies."

**Say the caveat yourself:** n=2 per evolved arm. The direction is clear, the
magnitude is not.

**The measurement bug worth mentioning:** before the log recorded which guidance
version wrote each draft, the aggregate showed 3.46 and 3.43 - two unremarkable
numbers that hid both the 100% ship rate and the regression. Third time in this
project that an aggregate averaged across a distinction that mattered.

Commands:
```bash
python -m agent.evolve            # analyse and propose
python -m agent.evolve --apply    # apply
python -m agent.evolve --history  # what changed and why
python run_agent.py --report      # the table above
rm data/angle_evolution.yaml      # revert everything
```


---

## Reach: who it writes to, and how it arrives

Two dimensions were added after the first build, because prospecting a company
and reaching a leader are not the same thing, and because every message being
an email is not an experiment.

**The target layer.** Each prospect carries a record in one of three states:
`named` (a verified person, every fact carrying a source URL), `role` (the
function, with the writer explicitly forbidden from inventing a person), or
`unknown`. The critic enforces it with a hard fail called
`invented_recipient` - any phrasing implying knowledge the record does not
hold.

> "Ask any model to write personally to the Head of CX at a company and it
> produces something warm about their career and current priorities. All
> invented, all fluent, and the recipient is the one person who knows it is
> invented. So a role with no person attached is treated as a constraint, not
> as a gap to fill."

**Five formats, across three channels.** Email and LinkedIn (digital), a
printed signal card (phygital), a personal micro-page (digital), and a
90-second walkthrough script (creative). Each carries its own constraints,
because a card cannot hold caveats in prose and a spoken script cannot lean on
a table.

**What happened on the card's first run:**

```
Printed signal card / Evidence audit
  round 1: REJECT  score 3.0  hard fails: format_violated
    "the back face is a cramped, jargon-heavy blob that likely breaks the
     70-word limit, and the offer is garbled"
  round 2: PASS  score 3.8
```

The critic caught a card written like an email. The card that shipped:

```
FRONT: 7.6%
       of negative smallcase reviews cite the support channel, not the product
BACK:  "...raised issue 45 days back, TKT-143999, still no resolution."
       Directional only: one snapshot, no contact volumes, reviews skew angry.
```

**What to say:**

> "The engine prospects companies, but the job is reaching leaders, so the
> recipient is its own layer with its own hard fail. And every message being an
> email is not an experiment, so format is a second dimension - the log keys on
> angle times format, which makes 'what moves senior leaders' a measured
> question. The card is the one I would actually bet on: it costs forty rupees,
> it carries their own ticket number, and it is the only channel where nobody
> else is competing for their attention."

**Say the caveat:** one card generated so far. The machinery is real, the
comparison is not yet.


---

## Questions you will get

**"Isn't the card a gimmick?"**
> "It would be if it were a mug. It carries one number from their own public
> reviews and their own ticket number, with the limitation printed on it. The
> argument isn't novelty, it's that it is the one channel where the competition
> is absent and the evidence still does the work."

**"How would you get their address?"**
> "Company registered office from the MCA filing or the website footer, marked
> to the role. I would not use a home address, and the record only holds what a
> public source states."

**"Did the self-improvement actually work?"**
> "On one angle, completely - target failure gone, ship rate 40 to 100%. On the
> other it backfired and introduced a new failure. Both are in the table. n is
> 2 per evolved arm, so treat the magnitude as directional."

**"So your project failed?"**
> "The hypothesis didn't survive. The engine worked — it's what killed it. I'd
> rather bring you a disconfirmed thesis I can evidence than a confirmed one I
> can't."

**"Why should I trust the numbers that are left?"**
> "Don't, entirely. Nine prospects have no data because I got their package IDs
> wrong. Reachability is one field out of three. It's one snapshot with no
> trend. Everything I'd want you to check is in the limitations section."

**"Why not use an LLM to classify?"**
> "Auditability. When a prospect asks how I concluded something about their
> support operation, I need a rule I can point at. And three of my four bugs
> were caught by reading what a rule matched — I'd never have spotted the
> five-star reviews inside a model's output."

**"Your agent escalates too much."**
> "The routed one does — 11% is useless commercially. That's why there's a
> third configuration. Integration turns a correct escalation into a correct
> answer, and that's the product argument."

**"How would you actually get a meeting with a CX head at a bank?"**
> "Not with this alone. The engine ranks and drafts; it doesn't get me in the
> room. The hook earns a reply because it contains a checkable fact about their
> own operation. After that it's the consultative conversation, which is the
> 60% of this job that nothing here automates."

**"You don't have 2–4 years."**
> "I don't. What I have is a year on the other side of this exact query class,
> and whatever you've just watched me build in an evening. I'd rather be judged
> on the second."

---

## Hard rules

- **Do not claim the TDS thesis is validated.** It isn't. Saying so is the one
  thing that could lose you the room, because it's checkable in your own repo.
- **Do not present the tax mechanics as settled law.** Say "as I understand it,
  and I'd verify before putting it in front of a client."
- **Volunteer the employer exclusion** before anyone asks: your current
  employer is left out of the prospect list on conflict-of-interest grounds,
  and no employer data of any kind is in this project. Say it without naming
  them unless they ask.
- **Lead with the bugs, don't wait to be asked.** They are the most senior
  thing in the repo.
- Don't oversell. It's a prototype built in an evening and saying so is
  stronger than pretending otherwise.

---

## Still to do before you present

1. Read the six cases in `evals/wealth_taxonomy.yaml` flagged
   `verify_before_demo: true` and correct my tax mechanics. **This is the one
   thing only you can do**, and it's the part most likely to get probed.
2. Optional: fix the nine wrong package IDs and re-collect. Adds data, doesn't
   change the argument.

---

## If you only remember one line

> "I built this to prove something, pointed it at real data, and it told me I
> was wrong. The engine's first useful output was catching its own author."
