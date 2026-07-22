import signal
import threading
from unittest.mock import Mock

import pytest

from warriors.management.commands import worker


def test_scheduler_death_stops_the_process(monkeypatch):
    """A crashed scheduler must take the process down for the platform to restart"""
    monkeypatch.setattr(worker, 'run_scheduler', Mock(side_effect=Exception('boom')))
    kill = Mock()
    monkeypatch.setattr(worker.os, 'kill', kill)

    with pytest.raises(Exception, match='boom'):
        worker.Command._run_scheduler(threading.Event())

    kill.assert_called_once_with(worker.os.getpid(), signal.SIGTERM)


def test_requested_stop_does_not_kill_the_process(monkeypatch):
    """Normal shutdown must not SIGTERM a process that is already stopping"""
    monkeypatch.setattr(worker, 'run_scheduler', Mock())
    kill = Mock()
    monkeypatch.setattr(worker.os, 'kill', kill)
    stop_event = threading.Event()
    stop_event.set()

    worker.Command._run_scheduler(stop_event)

    kill.assert_not_called()
