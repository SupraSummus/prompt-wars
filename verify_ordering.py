"""
Verify Battle warrior ordering.

lcs_len_X_Y_Z - what does Z mean?
  Interpretation A: Z = warrior_Z on the Battle model (warrior_1 = lower ID)
  Interpretation B: Z = Zth warrior in that direction (1st to go, 2nd to go)

These differ only for direction 2_1, where warrior_2 goes first.
We test both to see which one the data actually follows.
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
    [:100]
)

interp_a = 0  # Z = warrior_Z on Battle (w1 = lower ID always)
interp_b = 0  # Z = position in direction (1st/2nd to go)
neither = 0

for b in battles:
    w1 = b.warrior_1.body
    w2 = b.warrior_2.body
    result = b.text_unit_2_1.content

    stored_1 = b.lcs_len_2_1_1
    stored_2 = b.lcs_len_2_1_2
    lcs_w1 = lcs_len(w1, result)
    lcs_w2 = lcs_len(w2, result)

    a_matches = (lcs_w1 == stored_1 and lcs_w2 == stored_2)
    b_matches = (lcs_w2 == stored_1 and lcs_w1 == stored_2)

    if a_matches:
        interp_a += 1
    elif b_matches:
        interp_b += 1
    else:
        neither += 1

print(f"Direction 2_1 only (1_2 is unambiguous):")
print(f"  Interp A (Z = warrior_Z on Battle): {interp_a}")
print(f"  Interp B (Z = position in direction): {interp_b}")
print(f"  Neither: {neither}")
print()

# Also verify SHA where available (direction 2_1 = w2 goes first)
sha_ok = 0
sha_bad = 0
sha_absent = 0
for b in battles:
    if b.input_sha256_2_1 is None:
        sha_absent += 1
        continue
    w1 = b.warrior_1.body
    w2 = b.warrior_2.body
    # direction 2_1 means warrior_2 is concatenated first
    expected = sha256((w2 + w1).encode('utf-8')).digest()
    if expected == bytes(b.input_sha256_2_1):
        sha_ok += 1
    else:
        sha_bad += 1

print(f"SHA check for 2_1 (assuming w2 goes first):")
print(f"  OK: {sha_ok}, Bad: {sha_bad}, Absent: {sha_absent}")

# Count battles missing SHA fields
from django.db.models import Q
total = Battle.objects.count()
missing_1_2 = Battle.objects.filter(input_sha256_1_2__isnull=True).count()
missing_2_1 = Battle.objects.filter(input_sha256_2_1__isnull=True).count()
missing_both = Battle.objects.filter(input_sha256_1_2__isnull=True, input_sha256_2_1__isnull=True).count()
print(f"\nSHA coverage (total battles: {total}):")
print(f"  Missing input_sha256_1_2: {missing_1_2}")
print(f"  Missing input_sha256_2_1: {missing_2_1}")
print(f"  Missing both: {missing_both}")
print(f"  Have both: {total - missing_1_2 - missing_2_1 + missing_both}")
