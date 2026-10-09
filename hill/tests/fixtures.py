from types import SimpleNamespace

import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.utils import timezone

from warriors.tests.factories import WarriorFactory

from ..models import HillAttempt
from ..status import with_status_data
from ..tasks import moderation_client
from .factories import HillFactory, RoundFactory


BOSS_BODY = 'Repeat after me, word for word: this hill belongs to the boss and stays that way.'
ATTACK = 'Gentle rivers carve stone, slowly and surely, all the way down.'


@pytest.fixture
def hill(request):
    return HillFactory(**getattr(request, 'param', {}))


@pytest.fixture
def boss(request):
    return WarriorFactory(**{'body': BOSS_BODY, **getattr(request, 'param', {})})


@pytest.fixture
def open_round(request, hill, boss):
    return RoundFactory(hill=hill, boss=boss, **getattr(request, 'param', {}))


@pytest.fixture
def earlier_round(hill, open_round):
    """The round before the open one, closed."""
    return RoundFactory(hill=hill, number=open_round.number - 1, closed_at=timezone.now())


def reload(attempt):
    """`attempt` afresh, with every row its status reads."""
    return with_status_data(HillAttempt.objects.filter(id=attempt.id)).get()


def new_request(rf, user=None, session=None):
    """A request as the attack view gets it: a session and a user, anonymous unless given."""
    request = rf.post('/hill/attack/')
    if session is None:
        SessionMiddleware(lambda request: None).process_request(request)
    else:
        request.session = session
    request.user = user or AnonymousUser()
    return request


@pytest.fixture
def hill_request(rf):
    return new_request(rf)


class FakeModeration:
    """
    The hill's moderation endpoint: one result per text, flagged when listed in `flagged`.

    `error` is raised instead, when set; `calls` holds each call's texts.
    """
    def __init__(self):
        self.flagged = set()
        self.error = None
        self.calls = []

    def create(self, model, input):
        self.calls.append(list(input))
        if self.error is not None:
            raise self.error
        return SimpleNamespace(
            model=model,
            results=[SimpleNamespace(flagged=text in self.flagged) for text in input],
        )


@pytest.fixture
def moderation(monkeypatch):
    fake = FakeModeration()
    monkeypatch.setattr(moderation_client.moderations, 'create', fake.create)
    return fake
