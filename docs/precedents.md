# Prior art

Systems that already ran the pieces this project keeps proposing.
One entry each, ending in what transfers.
The arguments built on them:
`docs/twitter-for-prompts.md` (microblog reframe),
`docs/design-tensions.md` (novelty, adoption),
`docs/lineages.md` (ancestry),
`docs/rounds.md` (cadence).

**The mechanic is unoccupied.**
Nothing found publishes a machine blend
of two strangers' unprompted writing.
Adjacent: AI as the audience for a post,
AI combining two chosen inputs,
humans garbling each other in party games,
players attacking a model.
Weak evidence from few searches,
but there is no template to copy and no obituary to read.

**[Electric Sheep](https://en.wikipedia.org/wiki/Electric_Sheep)**
(Draves, from 1999) evolves fractal-flame animations
from arrow-key votes cast by screensaver viewers;
popular sheep are crossed and mutated, unpopular ones die,
and human "shepherds" steer the mating.
Transfers: fitness can come from spectators
at one keystroke with no account and nothing authored,
and a human hand on the tiller is part of the form.

**[Picbreeder](https://direct.mit.edu/evco/article/19/3/373/1371/Picbreeder-A-Case-Study-in-Collaborative)**
(2007–2021) let users continue evolving other users' published images.
Publishing was deliberate; branching recorded parentage at the branch.
Transfers: lineage recorded at adoption is exact and free.

**Quality-diversity search** defines the shortlist metric:
novelty as mean distance to the *k* nearest neighbors in an archive
([survey](https://arxiv.org/pdf/1708.09251)) —
computable on stored embeddings.
Its central claim, that optimizing novelty preserves
what optimizing fitness destroys,
is the central tension in `docs/design-tensions.md`
reached from the other side.

**[Infinite Craft](https://en.wikipedia.org/wiki/Infinite_Craft)**
(2024) went viral on two-input blending
with no opponent, rating, or leaderboard —
the reward is First Discovery credit for an untried pair.
Transfers: credit-for-novelty motivates this exact mechanical shape.

**[Emoji Kitchen](https://emojipedia.org/emoji-kitchen)**
is the most-loved two-input blend in consumer software,
and every combination is hand-drawn.
Warns: the median automatic blend is mush;
a blending product lives in the tail.

**Telephone games**
([Gartic Phone](https://en.wikipedia.org/wiki/Gartic_Phone)
and the exquisite-corpse lineage)
prove distortion-through-relay generates delight —
at the *reveal*, in a group, over a short chain.
This game has the distortion and no reveal,
which is what `docs/rounds.md` reaches for.

**[Renga](https://en.wikipedia.org/wiki/Renku)**
formalized fusion quality centuries ago:
a verse must link to the previous and shift away from it,
and the sōshō may reject a verse.
Transfers: link-and-shift is the pair of axes
`cooperation_score` in `warriors/score.py` measures,
and a curator with veto power is a feature of the form.

**[Sora's app and Meta's Vibes](https://www.cnn.com/2025/10/11/tech/openai-sora-2-meta-ai-slop-social-media)**
(2025) tested endless generated content as a feed:
mass launch, "AI slop" reception, steep decline, Sora discontinued.
Generation volume is not a retention mechanism.
[SocialAI](https://techcrunch.com/2024/09/17/socialai-offers-a-twitter-like-diary-where-ai-bots-respond-to-your-posts/)
adds the contrast: an audience of bots reads as a diary.
Here the counterpart is a real stranger,
which has to be visible or it might as well not exist.

**[PostSecret](https://www.cbsnews.com/news/postsecret-private-secrets-anonymously-shared-with-the-world/)**
is the anonymous-stranger feed that worked:
about twenty of a thousand weekly submissions published,
sequenced into an arc by one person, weekly, for two decades.
That is the cost of an editor —
and [@horse_ebooks](https://hyperallergic.com/trompe-ltweet-the-twitter-bot-world-horse_ebooks-left-behind/),
beloved as machine poetry and actually a person choosing posts,
is the same lesson twice.

**[Yik Yak](https://www.failory.com/cemetery/yik-yak)**
and Secret died of harassment;
[Whisper survived](https://www.fastcompany.com/40424834/how-whisper-survives-as-other-anonymous-social-apps-like-yik-yak-fail)
on moderation spending its competitors refused.
Anonymity plus a public feed has a fatal failure mode, not a shabby one.

**Gandalf's analytics dashboard**
was publicly reachable in 2023 with roughly 18 million prompts,
some
[containing email addresses](https://www.theregister.com/2023/09/17/gandalf_prompt_injection_game/).
Behavioral fact regardless of the dispute over it:
people type identifying details into a prompt box.
The game itself reports over a million players
against seven single-player levels and no social loop,
which is at least evidence that progression alone draws a crowd.

**[Tensor Trust](https://arxiv.org/abs/2311.01011)**
(2023) is the nearest competitor in mechanics
and shipped ~126k attacks and ~46k defenses as a dataset paper.
Its durable output is the dataset and the writeup —
the same floor the downside-protection argument
in `docs/strategy.md` names.

**AI-mediated communication research** finds an AI penalty:
text believed to involve AI reads as less trustworthy and less authentic,
and the effect bites hardest on readers scanning a mixed set
and guessing which items are machine-made
([overview](https://academic.oup.com/jcmc/article/25/1/89/5714020)).
The design response is to make the model the medium, not the author.
