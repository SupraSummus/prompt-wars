import uuid
from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.utils import timezone

from .models import (
    Job, LocalJob, _local_jobs, get_or_create_db_jobs, register_job, run,
    run_job,
)


@pytest.mark.django_db
def test_job_model():
    """Test Job model creation and fields"""
    job = Job.objects.create(key="test_job")
    assert isinstance(job.id, uuid.UUID)
    assert job.key == "test_job"
    assert job.last_run is None


def sample_handler(now):
    pass


def test_register_job():
    """Test job registration and automatic key generation"""
    assert not _local_jobs

    register_job(sample_handler, timedelta(minutes=30))
    assert len(_local_jobs) == 1

    local_job = _local_jobs[0]
    assert local_job.handler == sample_handler
    assert local_job.interval == timedelta(minutes=30)
    assert local_job.key == "django_scheduler.models_tests.sample_handler"


@pytest.mark.django_db
def test_run_executes_job_immediately():
    """Test job with no last_run gets executed immediately"""
    mock_handler = Mock()
    local_job = LocalJob(
        key="test_job",
        handler=mock_handler,
        interval=timedelta(minutes=30),
    )

    run([local_job], blocking=False)

    assert mock_handler.call_count == 1
    now = mock_handler.call_args[0][0]

    db_job = Job.objects.get(key="test_job")
    assert db_job.last_run == now


@pytest.mark.django_db
def test_job_not_run_if_interval_not_passed():
    """Test job isn't run if interval hasn't passed"""
    mock_handler = Mock()
    interval = timedelta(minutes=30)
    last_run = timezone.now() - timedelta(minutes=15)
    Job.objects.create(key="test_job", last_run=last_run)
    local_job = LocalJob(
        key="test_job",
        handler=mock_handler,
        interval=interval
    )

    run([local_job], blocking=False)
    mock_handler.assert_not_called()


@pytest.mark.django_db
def test_handler_error_rolls_back():
    """Test handler exceptions prevent last_run update"""
    mock_handler = Mock(side_effect=Exception("Boom!"))
    local_job = LocalJob(
        key="test_job",
        handler=mock_handler,
        interval=timedelta(minutes=30)
    )
    Job.objects.create(key="test_job")

    with pytest.raises(Exception):
        run_job(local_job)

    db_job = Job.objects.get(key="test_job")
    assert db_job.last_run is None


@pytest.mark.django_db
def test_get_or_create_db_jobs():
    """Test missing jobs get created in database"""
    local_jobs = [
        LocalJob(key="job1", handler=Mock(), interval=timedelta(minutes=30)),
        LocalJob(key="job2", handler=Mock(), interval=timedelta(minutes=60)),
    ]

    db_jobs = get_or_create_db_jobs(local_jobs)

    assert len(db_jobs) == 2
    assert Job.objects.filter(key="job1").exists()
    assert Job.objects.filter(key="job2").exists()


@pytest.mark.django_db
def test_non_blocking_exits_early(caplog):
    """Test non-blocking mode exits when jobs are in future"""
    Job.objects.create(
        key="future_job",
        last_run=timezone.now() - timedelta(minutes=29)
    )
    handler = Mock()
    local_job = LocalJob(
        key="future_job",
        handler=handler,
        interval=timedelta(minutes=30)
    )

    run([local_job], blocking=False)
    assert not handler.called
