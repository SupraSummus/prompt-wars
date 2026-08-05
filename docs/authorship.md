# Authorship of a blend

Law used as an instrument, not an obligation.
Doctrine is a map of configurations people have already had to settle;
where it has no mechanic,
the object in front of you is probably new.
Battle outputs sit in such a hole,
and the hole is specific enough to name —
which makes it a sharper claim of originality
than "Core War for LLMs".

## The configuration

Four properties at once:

1. two humans contributed expression;
2. neither consented to collaborate — each tried to erase the other;
3. a machine performed the combination;
4. how much of each contribution survived is measured and recorded
   (per direction and per algorithm, in `warriors/score.py`).

Property 4 is the rare one.
Property 2 is the one that breaks the doctrine
built for two-contributor works.
And because outputs are valid inputs,
shares compound across generations
(`docs/lineages.md`).

## Three doctrines, three answers, no tiebreaker

**Copyright authorship: nobody.**
Human authorship is required,
and for the purpose of authoring the *output*
prompts are treated as instructions conveying unprotectable ideas
([US Copyright Office, Part 2, 2025](https://www.dlapiper.com/en-us/insights/publications/2025/03/copyrightability-of-genai-outputs-in-the-us-key-developments));
the human-authorship requirement was affirmed in
[Thaler v. Perlmutter](https://media.cadc.uscourts.gov/opinions/docs/2025/03/23-5233.pdf)
with
[review denied](https://www.mayerbrown.com/en/insights/publications/2026/03/supreme-court-denies-review-in-ai-authorship-case).
EU law reaches the same place from originality:
no author's own intellectual creation, no protection
([EPRS overview](https://www.europarl.europa.eu/thinktank/en/document/EPRS_BRI(2025)782585)).
So the blend is an authorless artifact
with two identifiable contributors.

**Joint authorship: not applicable, by construction.**
A joint work requires the contributors to intend
that their contributions merge into a unitary whole
([Childress v. Taylor](https://law.justia.com/cases/federal/appellate-courts/F2/945/500/289853/)).
Players intend the opposite.
The one doctrine designed for two-contributor works
is excluded by the game's central mechanic,
and the leading framework for machine-assisted authorship
([Ginsburg and Budiardjo](https://btlj.org/data/articles2019/34_2/01_Ginsburg_Web.pdf))
analyses one human and a machine, not two humans in opposition.

**Contract: the operator.**
Model providers assign output rights to the API customer
([OpenAI](https://openai.com/policies/row-terms-of-use/),
[Gemini](https://ai.google.dev/gemini-api/terms)) —
here, the party that wrote none of it.
The two people who did write it are not parties to that assignment.

Contract says the operator,
copyright says nobody,
joint authorship declines the question,
and none of the three looks at the measured shares.
That is the gap.

## Why this is worth writing down

**It names what is actually novel.**
Not "AI mixes text" —
*measured, non-consensual, multi-author derivation,
recursively.*

**It gives the corpus a second market.**
`docs/strategy.md` treats the dataset as downside protection
for prompt-injection research.
This is a distinct claim on the same rows:
courts decline to quantify how much of a work survives into another,
and here that quantity exists by construction,
for hundreds of thousands of two-contributor artifacts with provenance.
An empirical instrument for a question doctrine avoids
is worth a writeup on its own.

**It converts attribution from compliance into design.**
There is no legal default to inherit,
so who gets the byline,
who may ask for a blend to be removed,
and what a repost carries
are all decisions.
`docs/twitter-for-prompts.md` takes the stance —
byline to the two writers, model as medium —
and the absence of doctrine is what makes that a stance
rather than a formality.

## Dead ends

**"Are we allowed to?"**
At this scale the compliance question decides nothing
the harassment evidence in `docs/precedents.md` does not already decide.

**Claiming operator ownership because the provider terms permit it.**
Cheap, and it contradicts the attribution stance,
which is the asset.

**Waiting for the law to settle before designing attribution.**
There is nothing to wait for:
the object precedes the doctrine.

**Treating prompts as owned property** —
licensing, exclusivity, infringement claims between players.
Whether a given warrior is protectable expression
is a separate question from the output-authorship one above
and turns on length and originality,
so it has no single answer across the corpus.
A game whose mechanic is copying each other's text
has nothing to gain from asking.

## Open

Is an output a derivative of the two prompts, a compilation, or nothing?
The similarity scores argue for the first;
the authorship doctrine points at the third.

Does the re-submission loop compound contribution shares
across generations,
and is there any framework that tracks that?
Nothing found does.

Cheapest test of the second-market claim:
show the measured-share corpus to one copyright scholar
and see whether the reaction is "so what" or "nobody has this".
