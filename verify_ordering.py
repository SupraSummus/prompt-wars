"""
Verify input_sha256 is consistent with lcs_len fields.

For each battle with SHA set, checks:
  1. sha256(w1.body + w2.body) == input_sha256_1_2
  2. sha256(w2.body + w1.body) == input_sha256_2_1
  3. lcs_len(w1.body, result_2_1) == lcs_len_2_1_1  (the tricky direction)
"""

from hashlib import sha256

from warriors.battles import Battle
from warriors.lcs import lcs_len


SAMPLE_SIZE = 100

battles = list(
    Battle.objects
    .select_related('warrior_1', 'warrior_2', 'text_unit_1_2', 'text_unit_2_1')
    .order_by('id')
    [:SAMPLE_SIZE]
)

print(f"Checking {len(battles)} battles (earliest by ID with SHA set)")

sha_ok = 0
sha_bad = 0
lcs_ok = 0
lcs_bad = 0

for b in battles:
    w1 = b.warrior_1.body
    w2 = b.warrior_2.body

    # SHA checks
    sha_1_2 = sha256((w1 + w2).encode('utf-8')).digest()
    sha_2_1 = sha256((w2 + w1).encode('utf-8')).digest()

    if (
        sha_1_2 == bytes(b.input_sha256_1_2 or b'') and
        sha_2_1 == bytes(b.input_sha256_2_1 or b'')
    ):
        sha_ok += 1
    else:
        sha_bad += 1
        print(f"SHA MISMATCH battle={b.id}")

    # LCS cross-check
    result_1_2 = b.text_unit_1_2.content
    result_2_1 = b.text_unit_2_1.content
    if (
        lcs_len(w1, result_1_2) == b.lcs_len_1_2_1 and
        lcs_len(w2, result_1_2) == b.lcs_len_1_2_2 and
        lcs_len(w1, result_2_1) == b.lcs_len_2_1_1 and
        lcs_len(w2, result_2_1) == b.lcs_len_2_1_2
    ):
        lcs_ok += 1
    else:
        lcs_bad += 1
        print(f"LCS MISMATCH battle={b.id}")

print(f"\nSHA: {sha_ok} ok, {sha_bad} bad")
print(f"LCS: {lcs_ok} ok, {lcs_bad} bad")
