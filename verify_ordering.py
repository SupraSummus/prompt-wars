"""
Dry-run verification script for battle warrior ordering.

The goal is to understand what mistake we could make when filling in
input_sha256 for old battles, and to cross-check using LCS.

There are two possible orderings for direction 1_2:
  A) "correct":  sha256(warrior_1.body + warrior_2.body)
  B) "swapped":  sha256(warrior_2.body + warrior_1.body)

For battles that already HAVE input_sha256 set, we check which ordering
matches, and verify that LCS values agree with the same interpretation.

For battles that DON'T have input_sha256, we use LCS recomputation to
figure out what the correct ordering is.

The naming convention in the Battle model:
  - lcs_len_1_2_1: LCS of warrior_1.body against text_unit_1_2 result
  - lcs_len_1_2_2: LCS of warrior_2.body against text_unit_1_2 result
  - lcs_len_2_1_1: LCS of warrior_1.body against text_unit_2_1 result
  - lcs_len_2_1_2: LCS of warrior_2.body against text_unit_2_1 result

If this is correct, then for direction 1_2 the input was
warrior_1.body + warrior_2.body, and:
  lcs_len_1_2_1 == lcs_len(warrior_1.body, result_1_2)
  lcs_len_1_2_2 == lcs_len(warrior_2.body, result_1_2)
"""

from hashlib import sha256

from warriors.battles import Battle
from warriors.lcs import lcs_len


SAMPLE_SIZE = 100


def verify_battle(battle):
    """
    Returns a dict with verification results for one battle.
    """
    results = {
        'battle_id': battle.id,
        'has_sha_1_2': battle.input_sha256_1_2 is not None,
        'has_sha_2_1': battle.input_sha256_2_1 is not None,
    }

    w1_body = battle.warrior_1.body
    w2_body = battle.warrior_2.body

    # --- Direction 1_2 ---
    if battle.text_unit_1_2 is not None:
        result_1_2 = battle.text_unit_1_2.content

        # Recompute LCS both ways
        lcs_w1_in_1_2 = lcs_len(w1_body, result_1_2)
        lcs_w2_in_1_2 = lcs_len(w2_body, result_1_2)

        results['dir_1_2'] = {
            'stored_lcs_1': battle.lcs_len_1_2_1,
            'stored_lcs_2': battle.lcs_len_1_2_2,
            'computed_lcs_w1': lcs_w1_in_1_2,
            'computed_lcs_w2': lcs_w2_in_1_2,
            'lcs_matches_normal': (
                lcs_w1_in_1_2 == battle.lcs_len_1_2_1 and
                lcs_w2_in_1_2 == battle.lcs_len_1_2_2
            ),
            'lcs_matches_swapped': (
                lcs_w2_in_1_2 == battle.lcs_len_1_2_1 and
                lcs_w1_in_1_2 == battle.lcs_len_1_2_2
            ),
        }

        # Check SHA if available
        if battle.input_sha256_1_2 is not None:
            sha_normal = sha256((w1_body + w2_body).encode('utf-8')).digest()
            sha_swapped = sha256((w2_body + w1_body).encode('utf-8')).digest()
            stored_sha = bytes(battle.input_sha256_1_2)
            results['dir_1_2']['sha_matches_normal'] = (sha_normal == stored_sha)
            results['dir_1_2']['sha_matches_swapped'] = (sha_swapped == stored_sha)
    else:
        results['dir_1_2'] = None

    # --- Direction 2_1 ---
    if battle.text_unit_2_1 is not None:
        result_2_1 = battle.text_unit_2_1.content

        # Recompute LCS both ways
        lcs_w1_in_2_1 = lcs_len(w1_body, result_2_1)
        lcs_w2_in_2_1 = lcs_len(w2_body, result_2_1)

        results['dir_2_1'] = {
            'stored_lcs_1': battle.lcs_len_2_1_1,
            'stored_lcs_2': battle.lcs_len_2_1_2,
            'computed_lcs_w1': lcs_w1_in_2_1,
            'computed_lcs_w2': lcs_w2_in_2_1,
            'lcs_matches_normal': (
                lcs_w1_in_2_1 == battle.lcs_len_2_1_1 and
                lcs_w2_in_2_1 == battle.lcs_len_2_1_2
            ),
            'lcs_matches_swapped': (
                lcs_w2_in_2_1 == battle.lcs_len_2_1_1 and
                lcs_w1_in_2_1 == battle.lcs_len_2_1_2
            ),
        }

        # Check SHA if available
        if battle.input_sha256_2_1 is not None:
            # Direction 2_1 means warrior_2 goes first
            sha_normal = sha256((w2_body + w1_body).encode('utf-8')).digest()
            sha_swapped = sha256((w1_body + w2_body).encode('utf-8')).digest()
            stored_sha = bytes(battle.input_sha256_2_1)
            results['dir_2_1']['sha_matches_normal'] = (sha_normal == stored_sha)
            results['dir_2_1']['sha_matches_swapped'] = (sha_swapped == stored_sha)
    else:
        results['dir_2_1'] = None

    return results


def main():
    # Get resolved battles with text units, random sample
    battles = list(
        Battle.objects.filter(
            resolved_at_1_2__isnull=False,
            resolved_at_2_1__isnull=False,
        ).exclude(
            finish_reason_1_2='error',
        ).exclude(
            finish_reason_2_1='error',
        ).select_related(
            'warrior_1',
            'warrior_2',
            'text_unit_1_2',
            'text_unit_2_1',
        ).order_by('?')[:SAMPLE_SIZE]
    )

    print(f"Sampled {len(battles)} resolved battles")
    print()

    # Counters
    counters = {
        '1_2': {'lcs_normal': 0, 'lcs_swapped': 0, 'lcs_neither': 0, 'lcs_both': 0,
                'sha_normal': 0, 'sha_swapped': 0, 'sha_neither': 0, 'sha_absent': 0},
        '2_1': {'lcs_normal': 0, 'lcs_swapped': 0, 'lcs_neither': 0, 'lcs_both': 0,
                'sha_normal': 0, 'sha_swapped': 0, 'sha_neither': 0, 'sha_absent': 0},
    }

    problems = []

    for battle in battles:
        r = verify_battle(battle)

        for direction in ('1_2', '2_1'):
            d = r[f'dir_{direction}']
            if d is None:
                continue

            c = counters[direction]

            # LCS classification
            if d['lcs_matches_normal'] and d['lcs_matches_swapped']:
                c['lcs_both'] += 1  # ambiguous (e.g. both warriors have same LCS)
            elif d['lcs_matches_normal']:
                c['lcs_normal'] += 1
            elif d['lcs_matches_swapped']:
                c['lcs_swapped'] += 1
                problems.append(('LCS_SWAPPED', direction, battle.id, d))
            else:
                c['lcs_neither'] += 1
                problems.append(('LCS_NEITHER', direction, battle.id, d))

            # SHA classification
            if f'sha_matches_normal' in d:
                if d['sha_matches_normal'] and not d['sha_matches_swapped']:
                    c['sha_normal'] += 1
                elif d['sha_matches_swapped'] and not d['sha_matches_normal']:
                    c['sha_swapped'] += 1
                    problems.append(('SHA_SWAPPED', direction, battle.id, d))
                elif not d['sha_matches_normal'] and not d['sha_matches_swapped']:
                    c['sha_neither'] += 1
                    problems.append(('SHA_NEITHER', direction, battle.id, d))
                # both matching means w1==w2 bodies, very unlikely
            else:
                c['sha_absent'] += 1

    # Print summary
    for direction in ('1_2', '2_1'):
        c = counters[direction]
        print(f"=== Direction {direction} ===")
        print(f"  LCS normal (correct):  {c['lcs_normal']}")
        print(f"  LCS swapped (WRONG):   {c['lcs_swapped']}")
        print(f"  LCS ambiguous (both):  {c['lcs_both']}")
        print(f"  LCS neither (ERROR):   {c['lcs_neither']}")
        print(f"  SHA normal (correct):  {c['sha_normal']}")
        print(f"  SHA swapped (WRONG):   {c['sha_swapped']}")
        print(f"  SHA neither (ERROR):   {c['sha_neither']}")
        print(f"  SHA absent:            {c['sha_absent']}")
        print()

    if problems:
        print(f"!!! {len(problems)} PROBLEMS FOUND !!!")
        for kind, direction, battle_id, data in problems[:10]:
            print(f"  {kind} dir={direction} battle={battle_id}")
            print(f"    stored:   lcs_1={data['stored_lcs_1']} lcs_2={data['stored_lcs_2']}")
            print(f"    computed: w1={data['computed_lcs_w1']} w2={data['computed_lcs_w2']}")
    else:
        print("No problems found. All orderings consistent.")


main()
