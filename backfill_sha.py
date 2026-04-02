"""
Backfill input_sha256 for battles missing it.

Convention (verified by verify_ordering.py):
  input_sha256_1_2 = sha256(warrior_1.body + warrior_2.body)
  input_sha256_2_1 = sha256(warrior_2.body + warrior_1.body)

Usage: set START_AFTER and BATCH_SIZE below, then run via manage.py shell.
Set DRY_RUN = True to preview without writing.
"""

from hashlib import sha256

from warriors.battles import Battle

START_AFTER = '00000000-0000-0000-0000-000000000000'
BATCH_SIZE = 100
DRY_RUN = True

battles = list(
    Battle.objects
    .filter(id__gt=START_AFTER)
    .filter(resolved_at_1_2__isnull=False, resolved_at_2_1__isnull=False)
    .exclude(finish_reason_1_2='error')
    .exclude(finish_reason_2_1='error')
    .select_related('warrior_1', 'warrior_2')
    .order_by('id')
    [:BATCH_SIZE]
)

filled = 0
skipped = 0

for b in battles:
    w1 = b.warrior_1.body
    w2 = b.warrior_2.body

    update_fields = []

    if b.input_sha256_1_2 is None:
        b.input_sha256_1_2 = sha256((w1 + w2).encode('utf-8')).digest()
        update_fields.append('input_sha256_1_2')

    if b.input_sha256_2_1 is None:
        b.input_sha256_2_1 = sha256((w2 + w1).encode('utf-8')).digest()
        update_fields.append('input_sha256_2_1')

    if not update_fields:
        skipped += 1
        continue

    if not DRY_RUN:
        b.save(update_fields=update_fields)
    filled += 1

last_id = battles[-1].id if battles else None
print(f"{'DRY RUN - ' if DRY_RUN else ''}Processed {len(battles)} battles: {filled} filled, {skipped} already had SHA")
print(f"Last ID: {last_id}")
print(f"To continue, set START_AFTER = '{last_id}'")
