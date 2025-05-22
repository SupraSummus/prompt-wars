# Warrior Lineages: Tracking Battle Result Ancestry

## Core Concept

Sometimes players copy-paste battle results as new warriors. We can track this lineage - warriors that are "born" from battle results but need to be liked by a human and given a chance to become actual warriors.

## The Challenge

Tracking lineage isn't straightforward because:

1. **Minor modifications**: Humans often make small changes to battle results before submitting them as warriors (adding newlines, minor tweaks)
2. **Multiple potential parents**: A warrior might be very similar to many different battle results
3. **Complex parentage**: Each battle involves a pair of warriors (A vs B, A vs C, A vs D), so a warrior's "parent set" could include warriors A, B, C, D, etc.

## Proposed Solution

Use **minhashing** or similar fuzzy matching techniques to detect similarity between:
- New warrior submissions 
- Existing battle results

This would allow detection of lineage even when humans make minor modifications to the original battle result.

## Lineage Structure

A single warrior could have multiple "parents" from various battles:
- Warrior W might be similar to battle results from battles (A vs B), (A vs C), (A vs D)
- This means W's ancestral "parent set" includes warriors {A, B, C, D}
- The lineage reflects both the battle results W resembles and the warriors that participated in those battles

## Human Selection Process

The system recognizes that:
1. Battle results exist as potential genetic material
2. Humans act as the selective force - choosing which results are interesting enough to become warriors
3. Only battle results that catch human attention and get adopted become part of the active warrior population

This creates a human-curated evolution where successful battle outputs propagate only when humans find them worthy of becoming new warriors.
