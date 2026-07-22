"""
Single entry point for all background work.

Two task systems share this process by design:
django_goals executes one-shot goals with retries and preconditions
(battles, embeddings), django_scheduler ticks fixed-interval jobs.
Unifying them — ticks as self-rescheduling goals — is rejected:
the busiest ticks fire every second (see warriors/scheduler.py),
and pushing a goal row through the goals machinery every second
is churn without simplification.
"""
import os
import signal
import threading

from django.core.management.base import BaseCommand
from django_goals.management.commands.goals_busy_worker import (
    stop_signal_handler,
)
from django_goals.management.commands.goals_threaded_worker import (
    threaded_worker,
)

from django_scheduler.models import run as run_scheduler


class Command(BaseCommand):
    help = 'Run the goals worker and the scheduler in one process'

    def add_arguments(self, parser):
        parser.add_argument('--threads', type=int, default=1)
        parser.add_argument(
            '--once',
            action='store_true',
            help='Exit when no work is available',
        )

    def handle(self, *args, **options):
        # One process instead of dedicated worker and scheduler containers
        # (docs/strategy.md, fixed compute). Multiple instances are safe:
        # scheduler jobs lock their DB row (see run_job).
        with stop_signal_handler() as stop_event:
            scheduler_thread = threading.Thread(
                target=self._run_scheduler,
                args=(stop_event,),
                name='scheduler',
            )
            scheduler_thread.start()
            try:
                threaded_worker(
                    worker_specs=[(options['threads'], None)],
                    stop_event=stop_event,
                    once=options['once'],
                )
            finally:
                # in --once mode the worker exits on its own;
                # the scheduler has no such mode, so stop it explicitly
                stop_event.set()
                scheduler_thread.join()

    @staticmethod
    def _run_scheduler(stop_event):
        try:
            run_scheduler(stop_event=stop_event)
        finally:
            if not stop_event.is_set():
                # The scheduler died while worker threads live on.
                # A dedicated scheduler container would be restarted
                # by the platform; stopping the whole process keeps
                # that supervision.
                os.kill(os.getpid(), signal.SIGTERM)
