"""
Verify that Battle warrior ordering is internally consistent.

For each sampled battle, recompute LCS and check it matches stored values.
If lcs_len(warrior_1.body, result_1_2) != battle.lcs_len_1_2_1, something is wrong.

Where input_sha256 is available, also verify sha256(w1.body + w2.body) matches.
"""

from hashlib import sha256

from warriors.battles import Battle
from warriors.lcs import lcs_len

battles = (
    Battle.objects
    .filter(resolved_at_1_2__isnull=False, resolved_at_2_1__isnull=False)
    .exclude(finish_reason_1_2='error')
    .exclude(finish_reason_2_1='error')
    .select_related('warrior_1', 'warrior_2', 'text_unit_1_2', 'text_unit_2_1')
    .order_by('?')[:100]
)

ok = 0
bad = 0

for b in battles:
    w1 = b.warrior_1.body
    w2 = b.warrior_2.body

    for direction, first, second, text_unit, stored_sha in [
        ('1_2', w1, w2, b.text_unit_1_2, b.input_sha256_1_2),
        ('2_1', w2, w1, b.text_unit_2_1, b.input_sha256_2_1),
    ]:
        result = text_unit.content
        stored_1 = getattr(b, f'lcs_len_{direction}_1')
        stored_2 = getattr(b, f'lcs_len_{direction}_2')
        computed_1 = lcs_len(first, result)
        computed_2 = lcs_len(second, result)

        lcs_ok = (computed_1 == stored_1 and computed_2 == stored_2)

        sha_ok = True
        if stored_sha is not None:
            expected = sha256((first + second).encode('utf-8')).digest()
            sha_ok = (expected == bytes(stored_sha))

        if lcs_ok and sha_ok:
            ok += 1
        else:
            bad += 1
            print(f"MISMATCH battle={b.id} dir={direction}")
            if not lcs_ok:
                print(f"  LCS stored=({stored_1}, {stored_2}) computed=({computed_1}, {computed_2})")
            if not sha_ok:
                print(f"  SHA does not match")

print(f"\n{ok} ok, {bad} bad (out of {ok + bad} checks)")
