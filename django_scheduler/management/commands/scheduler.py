from django.core.management.base import BaseCommand

from django_scheduler.models import run


class Command(BaseCommand):
    help = "Run scheduled jobs"

    def handle(self, *args, **options):
        run()
