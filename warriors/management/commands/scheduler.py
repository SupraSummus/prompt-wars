from django.core.management.base import BaseCommand

from warriors.scheduler import scheduler


class Command(BaseCommand):
    def handle(self, *args, **options):
        scheduler.run()
