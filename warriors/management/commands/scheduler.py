import signal

from django.core.management.base import BaseCommand

from warriors.scheduler import scheduler


class Command(BaseCommand):
    def handle(self, *args, **options):
        signal.signal(signal.SIGINT, lambda signum, frame: scheduler.clear())
        signal.signal(signal.SIGTERM, lambda signum, frame: scheduler.clear())
        scheduler.run()
