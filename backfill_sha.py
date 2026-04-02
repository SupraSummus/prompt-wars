"""
Backfill input_sha256 for battles missing it.

Convention (verified by verify_ordering.py):
  input_sha256_1_2 = sha256(warrior_1.body + warrior_2.body)
  input_sha256_2_1 = sha256(warrior_2.body + warrior_1.body)

Usage: run via manage.py shell.
Set REALLY_SAVE = False to preview without writing.
"""

from hashlib import sha256
from uuid import UUID

from django.db import transaction

from warriors.battles import Battle


BATCH_SIZE = 1000
REALLY_SAVE = True


@transaction.atomic
def do_chunk(start_from):
    battles = list(
        Battle.objects
        .filter(id__gte=start_from)
        .select_related('warrior_1', 'warrior_2')
        .order_by('id')
        .select_for_update(no_key=True)
        [:BATCH_SIZE]
    )

    filled = 0
    sha_already_set = 0

    for b in battles:
        w1 = b.warrior_1.body
        w2 = b.warrior_2.body

        input_sha_1_2 = sha256((w1 + w2).encode('utf-8')).digest()
        if b.input_sha256_1_2 is None:
            b.input_sha256_1_2 = input_sha_1_2
            filled += 1
        else:
            if bytes(b.input_sha256_1_2) != input_sha_1_2:
                print(f"WARNING: battle={b.id} has mismatching input_sha256_1_2")
            sha_already_set += 1

        input_sha_2_1 = sha256((w2 + w1).encode('utf-8')).digest()
        if b.input_sha256_2_1 is None:
            b.input_sha256_2_1 = input_sha_2_1
            filled += 1
        else:
            if bytes(b.input_sha256_2_1) != input_sha_2_1:
                print(f"WARNING: battle={b.id} has mismatching input_sha256_2_1")
            sha_already_set += 1

    if REALLY_SAVE:
        Battle.objects.bulk_update(battles, ['input_sha256_1_2', 'input_sha256_2_1'])

    print(start_from, 'filled:', filled, 'already set:', sha_already_set)

    last_id = battles[-1].id if battles else None
    return last_id


start = '00000000-0000-0000-0000-000000000000'
while start:
    start = do_chunk(start)
    if start:
        start = UUID(int=UUID(start).int + 1)  # start from the next ID
