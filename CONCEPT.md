# Prompt Wars: Concept and Developer's Introduction

## Project Overview

Prompt Wars (promptwars.io) is an innovative project that reimagines the classic Core Wars concept within the realm of large language models (LLMs). Created by Jan Rydzewski, this game/puzzle challenges players to craft prompts that manipulate LLMs in a competitive setting.

## Core Concept and Gameplay

Players create prompts ("spells") designed to subtly steer an LLM's response towards repeating the original prompt. Two players' prompts compete in a single LLM query, with victory determined by which prompt is most strongly represented in the output.

## Current State and Recent Insights

- The project continues to evolve based on observations and player feedback.
- Two major areas of potential change have been identified: game mechanics and content visibility.

## Potential Changes and New Features

1. **Removing "Unicode Cheesing"**:
   - Consideration to apply unicode normalization and equivalence, followed by lowercasing everything.
   - Aim: To level the playing field and focus on prompt engineering rather than unicode manipulation.

2. **Public Prompts and Battle Results**:
   - Proposal to make certain prompts and battle results public.
   - Benefits:
     - New players and spectators can learn from existing prompts.
     - Adds searchable content to the site, potentially improving discoverability.
   - Considerations:
     - Opt-in system to allow users to keep prompts private if desired.
     - Moderation concerns, though AI-generated content is less likely to be problematic.

## Challenges and Considerations

1. **Content Moderation**: 
   - Publishing user-generated content requires commitment to moderation.
   - Battle results may be safer to publish as AI-generated content is less likely to be scandalous.

2. **Balancing Openness and Privacy**:
   - Implementing an opt-in system for publishing battle results.
   - Allowing users to keep their prompts "top secret" if desired.

3. **Indexing and Searchability**:
   - Current issue: Indexing bots crawl the site but can't index meaningful content.
   - Consideration: Public battle results could provide searchable content, potentially contributing to the phenomenon described by the "dead internet" theory.

## Next Steps for Developers

1. Implement unicode normalization and lowercasing system to remove "unicode cheesing".
2. Develop a system for optionally publishing prompts and battle results.
3. Create a user interface for managing public/private status of prompts and battles.
4. Design and implement safety checks for public content to minimize moderation needs.
5. Optimize site structure and metadata to improve searchability of public content.
6. Explore ways to showcase interesting or humorous public battle results.
7. Develop tools for analyzing trends in public prompts and battle outcomes.

## Developer Engagement

1. The project remains open-source, available on GitHub: [GitHub - SupraSummus/prompt-wars](https://github.com/SupraSummus/prompt-wars)
2. Developers are encouraged to open issues or submit pull requests, especially for the new features being considered.
3. The creator continues to seek feedback and ideas for enriching the game mechanics and overall user experience.

Prompt Wars continues to evolve, offering unique opportunities for developers to explore LLM behavior, prompt engineering, and emergent gameplay mechanics. The proposed changes aim to create a more level playing field while potentially opening up the game's content to a wider audience. This balance of fairness, privacy, and openness presents interesting challenges for developers to tackle.

## Additional Documentation

For more detailed information on specific aspects of the project, please refer to the following documents:

- [SEO Strategies](docs/SEO.md): Our approach to improving search engine visibility and site discoverability.
