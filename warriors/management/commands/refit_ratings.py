"""
Refit every rating once, in one pass over every ranking.

The `update_rating` job refits the rating that moved most,
which keeps a settled ladder settled
but leaves alone a rating whose inputs changed without anything moving it:
after the set of battles a rating reads is redefined,
every rating is stale at once and none of them says so.
This pass refits each one;
run it again to converge further, as each refit moves its opponents.

Each refit is its own transaction,
so the pass holds no long locks and can be interrupted and rerun.
"""
from django.core.management.base import BaseCommand

from ...rating_models import WarriorRating


class Command(BaseCommand):
    help = 'Refit every rating once'

    def handle(self, *args, **options):
        ids = list(WarriorRating.objects.order_by('ranking', 'id').values_list('id', flat=True))
        for i, rating_id in enumerate(ids, start=1):
            rating = WarriorRating.objects.filter(id=rating_id).first()
            if rating is not None:
                rating.update_rating()
            if i % 1000 == 0:
                self.stdout.write(f'{i} of {len(ids)}')
        self.stdout.write(f'refit {len(ids)} ratings')
