# nugget-signal-engine

An AI-powered outbound engine for Nugget's BFSI pipeline, where the
personalisation is driven by evidence of the prospect's actual support pain
rather than by their LinkedIn headline.

Built 20 October 2026 by Bhavna Sharma as a working prototype for the Growth
Associate — Outreach and BD role.

---

## The thesis

Nugget was spun out of Eternal into Carthero Technologies in August 2026 and is
now a standalone enterprise-AI business. It closes roughly a deal a week on
inbound and reputation, with customers spanning private banks, insurance,
D2C and epharmacy. The thing it has never had to build is a repeatable outbound
motion. That is what this is a prototype of.

The wedge it prospects on comes from a finding the engine produces rather than
asserts:

> In Indian fixed-income wealth operations, a material share of support volume
> sits in a query class where the correct automated behaviour is to refuse or
> escalate. Vendors reporting **deflection rate** cannot see this class, because
> a confidently wrong answer to a tax or settlement question scores as a
> successfully deflected ticket.

Nugget's published Wealth page covers onboarding (CKYC, DigiLocker, eSign),
product discovery, and investor support (portfolio summaries, ticket triage,
human handoff). It does not address this class. That is an unworked wedge, not
a contested one.

## The finding

Three agent configurations against the same 18-case taxonomy:

| Configuration        | Automated | Correctly disposed | Confidently wrong |
|----------------------|-----------|--------------------|-------------------|
| Naive retrieval      | 67%       | 39%                | 8                 |
| Routed               | 11%       | 83%                | 0                 |
| Routed + integrated  | 72%       | 94%                | 0                 |

Naive retrieval and the integrated agent automate almost the same share. On a
deflection-rate slide they are the same product. One is correct 39% of the time
with eight confidently wrong tax and settlement answers; the other is correct
94% with none.

Routing alone is not the answer either. It is safe and automates 11%, which is
not a product. The value is routing first, then integrating so that the correct
route is usually an answer.

---

## Running it

```bash
pip install google-play-scraper pyyaml

# 1. Collect real signals (needs unrestricted network)
python -m src.collect_playstore

# 2. Classify reviews into pain signals
python -m src.classify

# 3. Score and rank the pipeline
python -m src.score

# 4. Run the agent eval harness
python -m src.run_evals

# 5. Generate outreach sequences
python -m src.generate_messages --top 5
```

If the Play Store is unreachable, step 1 marks every record `unreachable` and
nothing downstream is scored. To exercise the pipeline without network access:

```bash
python -m src.make_fixture   # SYNTHETIC data, clearly flagged at every layer
```

The message generator will then **refuse to run** until you pass
`--i-know-this-is-fake`.

---

## Design decisions worth defending

**No invented numbers.** Every metric is either collected or `null` with a
recorded reason. Nothing is defaulted to a plausible value.

**Missing signals reduce confidence rather than being treated as average.**
Most prospecting tools silently promote prospects they know nothing about into
the middle of the queue. Here, `confidence` is the ratio of signals collected
to signals possible, it multiplies the final score, and below 0.60 the prospect
is held out of the outreach queue entirely.

**The message generator refuses to run on synthetic data.** The failure this
prevents is a fluent, personalised message citing a complaint statistic about a
named company that was never measured, arriving in that company's inbox.

**The eval scores disposition correctness, not deflection rate.** Severity
order, worst first: `confidently_wrong` > `missed_escalation` >
`over_escalation` > `correct`. A system optimising deflection ranks
`confidently_wrong` as a success.

**Keyword classification, not an LLM.** Slower to build and less accurate, but
deterministic and auditable. When a prospect asks how you reached a conclusion
about their operation, the answer is a rule you can point at.

**No LinkedIn scraping.** It breaches their terms. Reachability is manual and
human-verified. Demoing a ToS-violating scraper to a company selling into
SEBI/RBI/IRDAI-regulated buyers would argue against its own compliance story.

---

## Conflicts and data hygiene

Wint Wealth is **deliberately excluded** from the prospect universe. The author
is currently employed there, and including an employer in a prospect list built
for a third party is a conflict of interest.

**No employer data of any kind is used in this project** — no tickets, no
volumes, no transcripts, no aggregate statistics. The query taxonomy in
`evals/wealth_taxonomy.yaml` is reconstructed from publicly observable query
patterns and from general domain knowledge of Indian fixed-income mechanics. It
contains nothing proprietary.

---

## Three bugs found while building, kept in the history

**ICP fit returned 100 for all 31 prospects.** The vertical base was 100, the
regulator and sub-vertical bonuses were added on top, and the total was clamped
at 100 — so every bonus was discarded. A factor that returns the same value for
every row is a constant, not a factor. Fixed by lowering the base to ~60.

**The confidence layer reported 1.00 across a universe with no reachability
data.** It counted reachability as one signal if *any* sub-field was present,
and `company_size_band` is pre-filled for everyone. The layer built specifically
to be honest about thin evidence reported total confidence in evidence that did
not exist, and the output looked entirely normal. Fixed by counting sub-signals
individually against a ratio.

**The eval scored the integrated agent as worse than the naive baseline.**
Answering a trap query from the user's own ledger and answering it from a
generic FAQ both registered as `answered`. Those are opposite behaviours. The
metric was measuring a proxy — *did it answer?* — instead of what matters: *did
it answer from evidence about this user?* Fixed by judging on answer source.

The third is the most instructive: a new agent configuration exposed that the
measurement itself was wrong. That is most of what eval work actually is.

---

## Known limitations

- Pain signals in the committed output are **synthetic**. Run the collector.
- Reachability is scored on size band alone; the two fields that matter are
  null across all 31 prospects, which is why confidence caps at 0.78.
- App reviews are a biased sample — skewed toward angry and resolved-badly.
  Review share is directional evidence of support strain, not a measure of
  contact volume or real resolution rates.
- Keyword classification will miss code-switched and transliterated complaints,
  which in Indian consumer apps is a material share of the corpus.
- The eval scores routing structure, not substantive tax correctness. Cases
  flagged `verify_before_demo: true` contain India-specific mechanics that must
  be confirmed against current law before being presented.

## Next, if this were real

1. Run the collector weekly; track signal *deltas* rather than levels. A
   support surface degrading month over month is a far stronger buying trigger
   than one that is merely bad.
2. Add RBI Ombudsman and SEBI SCORES complaint data — slower to parse, far more
   credible to a senior operator than app reviews.
3. Replace keyword classification with a small fine-tuned classifier once there
   is labelled data, keeping the keyword path as the auditable fallback.
4. Instrument reply rates per hook type to learn which evidence class actually
   earns a response. The engine currently assumes the hard-query hook is the
   strongest; that is a hypothesis, not a result.
