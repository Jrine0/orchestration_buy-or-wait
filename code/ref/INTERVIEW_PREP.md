# INTERVIEW_PREP.md

Personal notes. **Do not ship this in `code.zip`.**

Format: live, 30 minutes, camera on, opens after submission and stays open 12
hours. The judge has your submission and may ask about your approach, your
decisions, and **how you used AI while building the solution**. That last one is
explicitly in scope, so have a real answer about your own process, not just the
system's.

Worth 30 of 100 — the same as the CSV. Prepare for it like it is.

## Setup before the call

- `code/case_files/` open in an editor with fuzzy file search ready, so any
  `request_id` is two keystrokes away. The case files are **your** instrument
  here; the judge will not be running your code.
- `SPEC_RULES.md` open in a second pane. When asked "how do you handle X",
  answering with a rule ID and pointing at the enforcing module is the strongest
  possible form of the answer.
- `evaluation/dataset_report.md` open. Concrete counts beat adjectives.
- Pick three interesting rows in advance: one `affordable_now`, one
  `not_recommended` or `wait`, one where an orphan message changed the outcome.
  Know their binding constraints cold.

## Questions to have crisp answers for

**"Where does the LLM actually make a decision?"**
Nowhere. Two bounded jobs: reading values off images, and disambiguating free
text the rule layer could not parse. Both produce facts that enter a
deterministic engine. A 90-day balance forecast is arithmetic; asking a model to
decide it adds variance with no upside. Say this plainly — it is a strength, not
a hedge.

**"Why did user X get `wait` instead of `full_payment`?"**
Open the case file, name the binding date and the binding event. Do not
narrate — show the constraint.

**"What if their balance were 20% higher?"**
Re-run the engine live on a perturbed input. This is cheap precisely because the
engine is pure, and it is the single most convincing thing you can demonstrate.
Have the command ready.

**"How do you know you are not overfit to the 25 samples?"**
The distribution check on all 250, plus the policy that the samples are used as
an invariant suite and a format oracle rather than a fitting set. Mention the
inversion: a ground-truth row failing one of our invariants means the invariant
is wrong.

**"Is your category vocabulary hardcoded?"**
No — derived at runtime from the distinct categories in `financial_events.csv`
with an n-gram fallback. Point at the line.

**"How does retrieval handle a message it cannot place?"**
It abstains on a thin top-1/top-2 margin and falls through to the spec's own
"financially safer interpretation" rule. A system that says "I could not place
this" is more trustworthy than one that always produces a match.

**"What about prompt injection in the messages?"**
Structural answer, not a prompt answer: the model never touches a scored field,
so an adversarial message has nothing to hijack. The prompt instruction is
belt-and-braces.

**"What is weak, and what would you do with another day?"**
Have this ready and be specific — smoothing on noisy categories, cadence
tolerance, reduction sizing. Volunteering real limitations reads as competence.
Vagueness here is the most common way people lose these points.

**"How did you use AI to build this?"**
Concrete process answer: where you used the agent, where you overrode it, what
you cross-checked and how, what it got wrong. The cross-check pass that produced
the spec-rule audit is a genuinely good story. Do not oversell autonomy — show
judgment.

**"Why TF-IDF and not embeddings?"**
Offline, deterministic, free, auditable — every match has a traceable score in
the case file. The interface is swappable for a real embedding model without
changing any caller. On a corpus this small, recall was not the constraint;
precision and abstention were.

## Framing for the whole thing

Retrieval and the graph reconstruct an individual's financial state from messy,
partially linked, multimodal evidence — that is the part that generalizes across
users and institutions. The decision itself is deterministic arithmetic over
that state, because it is not a judgment call. The two layers are separate so
either can be swapped: a different bank or schema changes the loader adapter and
the vocabulary, not the engine.

Say that in the first two minutes. It sets the frame for everything after it.
