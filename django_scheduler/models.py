import datetime
import inspect
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Callable

from django.db import models, transaction
from django.utils import timezone


logger = logging.getLogger(__name__)


class Job(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField(max_length=100, unique=True)
    last_run = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['key']


@dataclass(frozen=True)
class LocalJob:
    """
    A job as defined in current process
    """
    key: str
    handler: Callable
    interval: datetime.timedelta


_local_jobs = []


def register_job(handler, interval, key=None):
    job = get_job_from_function(handler, interval, key)
    _local_jobs.append(job)


def get_job_from_function(handler, interval, key=None):
    if key is None:
        key = inspect.getmodule(handler).__name__ + '.' + handler.__name__
    return LocalJob(key=key, handler=handler, interval=interval)


def run(local_jobs=None, blocking=True):
    if local_jobs is None:
        global _local_jobs  # noqa: F824
        local_jobs = _local_jobs.copy()
        del _local_jobs  # prevent adding more jobs after we started

    # build a queue of jobs to run
    db_jobs = get_or_create_db_jobs(local_jobs)
    queue = []
    now = timezone.now()
    for local_job in local_jobs:
        db_job = db_jobs[local_job.key]
        if db_job.last_run:
            next_run = db_job.last_run + local_job.interval
        else:
            next_run = now
        queue.append((next_run, local_job))
    queue.sort(key=lambda x: x[0])
    del db_jobs
    del local_jobs

    logger.info("Starting scheduler. Jobs: %s", [job.key for _, job in queue])

    # run jobs
    while True:
        now = timezone.now()
        if not queue:
            logger.info("No jobs in queue, exiting")
            break

        next_run, local_job = queue[0]
        if next_run > now:
            if not blocking:
                logger.info("Next job is in the future, exiting")
                break
            time_to_sleep = (next_run - now).total_seconds()
            logger.info("Sleeping for %s seconds until next job %s", time_to_sleep, local_job.key)
            time.sleep(time_to_sleep)

        next_run, local_job = queue.pop(0)
        db_job = run_job(local_job)

        queue.append((db_job.last_run + local_job.interval, local_job))
        queue.sort(key=lambda x: x[0])


def get_or_create_db_jobs(local_jobs):
    db_jobs = {
        db_job.key: db_job
        for db_job in Job.objects.filter(
            key__in=[local_job.key for local_job in local_jobs]
        )
    }
    for local_job in local_jobs:
        if local_job.key not in db_jobs:
            logger.info("Creating missing DB job entry, key=%s", local_job.key)
            db_job = Job(key=local_job.key)
            db_job.save()
            db_jobs[local_job.key] = db_job
    return db_jobs


@transaction.atomic
def run_job(local_job):
    db_job = Job.objects.filter(
        key=local_job.key,
    ).select_for_update(
        no_key=True,
    ).first()
    if not db_job:
        db_job = get_or_create_db_jobs([local_job])[local_job.key]

    now = timezone.now()
    if db_job.last_run:
        next_run = db_job.last_run + local_job.interval
        if next_run > now:
            logger.info("Job %s is not due yet, skipping", local_job.key)
            return db_job

    logger.info("Running job %s", local_job.key)
    try:
        with transaction.atomic():  # savepoint protects from transaction errors in handler
            local_job.handler(now=now)
    except Exception:
        logger.exception("Error running job %s", local_job.key)
    db_job.last_run = now
    db_job.save(update_fields=['last_run'])
    return db_job
