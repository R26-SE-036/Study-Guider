# Study Guider: what the proposal promised vs what exists

Checked against `R26-SE-036_IT22230942_Madurapperuma H A S I_Version_2.docx`,
by reading the code and by calling every endpoint on a running instance.

Written in plain English on purpose. Nothing here is a criticism of the design —
it is a list of the distance between the document and the running system, so you
can decide what to build, what to cut, and what to rewrite in the document.

---

## The short version

| # | Proposal requirement | Status |
|---|---|---|
| FR-01 | Collect error IDs, repeat counts, time between runs | **Done.** Timing added |
| FR-02 | ~~Ingest engagement from Gamification + Collaborative~~ | **Withdrawn** — claim removed |
| FR-03 | Random Forest classifies struggle Low/Medium/High every 30s | **Different thing built** |
| FR-04 | Trigger on 3 repeats of one concept, or sustained High | **Done**, but by Code Coach |
| FR-05 | Graph RAG — vector DB *and* knowledge graph | **Done.** Graph context now in the prompt |
| FR-06 | Auto-generate a quiz after each lesson | **Done.** Two answer shapes fixed; see caveat |
| FR-07 | Track time spent on the lesson | **Done** |
| FR-08 | Update mastery using Knowledge Tracing | **Done.** Bayesian Knowledge Tracing |
| FR-09 | IDE card → web dashboard | **Done.** Navigation was missing; now built |
| NFR-01 | Lesson + quiz in under 5 seconds | **Missed.** Now 18–48s on a thinking model |
| NFR-02 | Struggle model F1 ≥ 0.75 | **Not measurable as written** |
| NFR-03 | 100% grounded in the syllabus vector DB | **All 14 concepts now have notes** |
| NFR-04 | SUS score above 68 | **Not tested** |
| NFR-05 | Anonymised, raw source code never sent | **Done** |
| NFR-06 | Available 24/7 | **Blocked** — see the quota problem |

---

> **Updated after the implementation pass.** FR-01, FR-05, FR-07 and FR-08 are
> now built, the prerequisite graph has been seeded into Neo4j, and all 14
> concepts have syllabus material. FR-02 was withdrawn rather than built. The
> sections below still describe what was found, with current status noted.

## The two that will hurt you most

### 1. The Gemini free tier allows 20 requests per day. Total.

Not per user. Not per minute. **Twenty generate-content calls per day for the
whole project**, and every lesson and every quiz is one call.

```
Quota exceeded for metric: generate_content_free_tier_requests, limit: 20
quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier
```

I hit this during testing. Ten lessons and ten quizzes and the service is done
for the day, for everyone.

This makes NFR-06 (24/7 availability) impossible as things stand, and it means a
viva demo can fail simply because you rehearsed it that morning. It needs a
decision before deployment — see the questions at the end.

### 2. Lessons take 13–30 seconds. The proposal says 5.

Measured on a running instance:

- micro-lesson generation: **29.4s**, then **13.8s**, then **30.2s**
- quiz generation: **13.8s** and **22.3s**

NFR-01 says "generated and displayed within a 5-second window to maintain
learning momentum". That is not close, and it is not a tuning problem — a single
`gemini-2.5-flash` call producing a 476-word explanation plus a diagram takes
that long. Either the number in the document changes, or the design does
(pre-generate lessons for common errors, stream the text as it arrives, or use a
faster model for the quiz).

---

## Bugs found while testing

**The quiz was broken about half the time.** `POST /api/quiz/generate` returned
503 "No usable questions were generated" while the model was in fact returning
four perfectly good questions. The cause: the model sometimes writes
`"correct_answer": "B"` and sometimes the full option text, and the code
demanded an exact string match, so every question was thrown away and the whole
quiz failed.

It is worse than an error, because of what a quiz decides here: the score is
what resolves a remediation trigger. A quiz that will not generate blocks the
student; a quiz whose answers do not match its options would have marked every
answer wrong.

Fixed, with 15 tests pinning it. Two answer shapes are now handled — a bare
letter, and a letter followed by the option text where the options have no
letters. **Two of six live runs still failed**, and I could not diagnose further
because the daily quota ran out. Treat the quiz as "mostly fixed, not proven".

**The prerequisite graph does not exist in the database.** Neo4j reports:

```
The relationship type `PREREQUISITE_OF` does not exist in database
```

So `GET /api/progress/me/learning-path` always answers "no prerequisites, start
here" regardless of the concept. The 17 hand-written edges are in
`app/core/concepts.py` but were never loaded — `migrate_graph.py
--with-prerequisites` has not been run. This is a one-command fix, not a code
change, but until it is run the learning-path feature returns nothing useful.

**`/api/progress/me/learning-path` needs a `concept` parameter and does not say
so.** Called without one it returns a 422 with a raw validation blob. Minor, but
it is the kind of thing a demo trips over.

---

## The gaps, one by one

### FR-02 — Cross-component data ingestion — **missing**

The proposal says Study Guider ingests "engagement metrics from the Gamification
and Collaborative modules". It does not. It reads remediation triggers and
diagnostics from Code Coach and nothing else. There is no code path that has
ever contacted the Gamification Engine or Collaborative Studio.

Either build it, or narrow the claim to "ingests logical performance metadata
from Code Coach".

### FR-03 — The struggle classifier — **a different thing was built**

This is the most important mismatch in the document, and it needs care in the
write-up.

The proposal describes a Random Forest that reads error patterns and attempt
frequency and outputs **Low / Medium / High struggle**, re-evaluated **every 30
seconds**.

What exists is a Random Forest that outputs **High Cognitive Load / Needs Simple
Basics / Minor Syntax Error**. It runs **once, when a lesson is requested**. Its
only job is to set the tone of the generated lesson — simpler wording versus a
terse correction. There is no 30-second loop anywhere in the system.

The Low/Medium/High struggle level *does* exist, but it is computed by **Code
Coach**, not here, and by a rule rather than a model.

So the sentence "a Random Forest classifies struggle into Low/Medium/High" is
not true of this component. What is true: "a Random Forest selects the
pedagogical register of the lesson; struggle level is supplied by Code Coach".

### FR-05 — "Graph RAG" — **half of it**

Retrieval works: syllabus text is chunked, embedded, and stored in a Neo4j
vector index, and the closest chunks go into the lesson prompt. That is RAG, and
it runs.

The **Graph** half does not. The proposal says the pipeline "queries both the
vector database for syllabus content **and the Skill Knowledge Graph for
individual context**". The lesson prompt receives no student-specific graph
data — not their mastery, not their prerequisite gaps, not their history. It
gets retrieved syllabus text, the error type, an example snippet, and the
cognitive state.

Calling it "Graph RAG" in the write-up is a stretch. Either feed the student's
graph context into the prompt (a genuinely small change, and it would make the
lessons noticeably more personal), or describe it as "vector RAG over a
syllabus stored in Neo4j".

Also worth noting: the proposal names **ChromaDB/Pinecone** as the vector store.
Neither is used. The vectors live in Neo4j's own vector index, which removed a
whole service and a directory that had to survive restarts — a good change, but
the document says otherwise.

### FR-07 — Remediation monitoring — **missing the "how long" half**

Quiz accuracy is tracked. Time spent on the lesson is not — nothing records when
a lesson was opened versus when the quiz was submitted. The proposal asks for
both, and the SQKT reference in §3.2 leans on it.

The data needed is one timestamp at lesson open and one at quiz submit. The
`lesson-opened` endpoint already fires; it just does not store a time that is
later compared.

### FR-08 — Knowledge Tracing — **simplified to an average**

The proposal repeatedly promises Knowledge Tracing — a model (BKT, DKT or
similar) that *predicts* future performance from a history of attempts.

What exists: each quiz attempt is written to Neo4j as an `ATTEMPTED`
relationship with a percentage, and mastery is the average. That is a
gradebook, not knowledge tracing. Nothing predicts anything.

This is a real research-claim gap. Averaging is defensible and simple, but it
cannot be described as Knowledge Tracing or as predicting future performance.
Also, "Formal Concept Analysis is applied to structure these concepts into a
hierarchical learning path" (§3.2) — no Formal Concept Analysis exists anywhere
in the code.

### NFR-02 — F1 ≥ 0.75 — **cannot be measured as written**

The target applies to the struggle detection model. Since the model that exists
classifies something else (see FR-03), there is no F1 for the thing the document
is describing.

The cognitive-state model that *does* exist reproduces its own rubric at ~1.00,
which is a fidelity check, not accuracy against students — the model card says
so in those words.

### NFR-03 — 100% grounded, no hallucination — **not enforced**

Syllabus chunks go into the prompt. Nothing checks that the generated lesson
actually used them, and there is no citation, no grounding score and no
rejection path. The `data/` folder holds **two** syllabus files —
`conditionals.txt` and `loop_boundaries.txt` — covering 2 of the 14 concepts.
For the other twelve, retrieval returns whatever is nearest, which may be
unrelated.

So a lesson on `switch_statements` is currently ungrounded in practice, whatever
the pipeline does.

### NFR-04 — SUS above 68 — **not tested**

No usability study has been run. This is a normal thing to still owe at proposal
stage, but the write-up should not imply it is done.

---

## What was removed, and why

Cleaned out as part of this pass, because it was dead rather than unfinished:

| Removed | Reason |
|---|---|
| `frontend/` (25 files) | Replaced by the one web tier; the Study pages live in `codeguru-web` |
| CORS middleware + `CORS_ORIGINS` | No browser calls this service — the web app calls it server-side |
| `OPENROUTER_API_KEY` | Generation moved to Gemini; nothing read it |
| `CODE_COACH_CLIENT_NAME` | Declared and documented, never referenced |
| `test_models.py` | A throwaway script to list Gemini models, named so pytest collected it |

`data/dataset.csv` was kept: it is the ten handwritten rows the rubric replaced,
and `generate_rubric_dataset.py --check` still compares the rubric against them.
That comparison is worth keeping — it is what found two holes in the rubric.

---

## Questions I need answered

1. **The 20-a-day Gemini quota.** Options: pay for a Gemini key; switch to a
   model with a larger free allowance; cache aggressively so repeated errors
   reuse one lesson; or accept it and state it as a limitation. This changes the
   deployment plan, so it is your call.

2. **FR-03.** Do you want me to build the Low/Medium/High struggle classifier
   the proposal describes, or update the document to describe the
   cognitive-state model that exists? Building it is real work; the trigger
   logic that would use it already lives in Code Coach.

3. **Knowledge Tracing.** Same question. Implementing BKT over the existing
   `ATTEMPTED` relationships is a contained piece of work and would make FR-08
   true. Or the claim narrows to "mastery averaging".

4. **The missing syllabus content.** Two of fourteen concepts have material. Do
   you want to write the other twelve? Without them NFR-03 cannot hold.
