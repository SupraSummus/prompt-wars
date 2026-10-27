import datetime

import pytest
from django.contrib.sessions.models import Session
from django.urls import reverse
from django.utils import timezone

from .session_middleware import REFRESHED_ON_KEY


@pytest.mark.parametrize(('refreshed_days_ago', 'extended'), [(1, True), (0, False)])
@pytest.mark.django_db
def test_visit_extends_session_once_a_day(client, refreshed_days_ago, extended):
    refreshed_on = timezone.localdate() - datetime.timedelta(days=refreshed_days_ago)
    session = client.session
    session[REFRESHED_ON_KEY] = refreshed_on.isoformat()
    session.save()
    soon = timezone.now() + datetime.timedelta(hours=1)
    Session.objects.update(expire_date=soon)

    client.get(reverse('data_policy:root'))

    assert (Session.objects.get().expire_date > soon) == extended


@pytest.mark.django_db
def test_visitor_without_session_gets_none(client):
    response = client.get(reverse('data_policy:root'))

    assert not Session.objects.exists()
    assert 'sessionid' not in response.cookies


@pytest.mark.django_db
def test_expired_session_is_not_revived(client):
    client.cookies['sessionid'] = 'x' * 32

    # A slash redirect: no view loads the session before the middleware does.
    client.get(reverse('data_policy:root').rstrip('/'))

    assert not Session.objects.exists()


@pytest.mark.django_db
def test_logout_is_not_undone(user_client):
    user_client.post(reverse('logout'))

    assert not Session.objects.exists()
