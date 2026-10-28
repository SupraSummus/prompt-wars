import pytest
from django.contrib.auth import get_user
from django.test import Client
from django.urls import reverse

from warriors.models import WarriorUserPermission
from warriors.tests.factories import (
    WarriorFactory, WarriorUserPermissionFactory,
)

from ..models import GoogleAccount, User
from .factories import UserFactory
from .test_google_login import log_in_with_google, signed_token


PASSWORD = 'a long and unusual password'


@pytest.fixture
def password_account():
    user = UserFactory(username='fokr')
    user.set_password(PASSWORD)
    user.save()
    return user


@pytest.fixture
def google_only(client, google):
    """The second account: made by logging in with Google first, and logged in in `client`."""
    log_in_with_google(client, signed_token(google, sub='google-sub'))
    return get_user(client)


def connect(client, password=PASSWORD):
    return client.post(reverse('connect_password:connect'), {'username': 'fokr', 'password': password})


@pytest.mark.django_db
def test_my_prompts_offers_connecting_to_a_google_only_account(client, google_only, password_account):
    assert 'Connect a password account' in client.get(reverse('my_warriors:index')).content.decode()
    client.force_login(password_account)
    assert 'Connect a password account' not in client.get(reverse('my_warriors:index')).content.decode()


@pytest.mark.django_db
def test_the_password_account_takes_over_the_google_only_one(client, google, google_only, password_account):
    created = WarriorUserPermissionFactory(user=google_only, warrior__created_by=google_only).warrior

    assert connect(client).url == reverse('my_warriors:index')

    assert get_user(client) == password_account
    assert WarriorUserPermission.objects.get(warrior=created).user == password_account
    created.refresh_from_db()
    assert created.created_by == password_account
    google_only.refresh_from_db()
    assert not google_only.is_active
    client.post(reverse('logout'))
    log_in_with_google(client, signed_token(google, sub='google-sub'))
    assert get_user(client) == password_account


@pytest.mark.django_db
def test_a_prompt_both_hold_keeps_the_password_accounts_choices(client, google_only, password_account):
    warrior = WarriorFactory(public_battle_results=True)
    WarriorUserPermissionFactory(user=password_account, warrior=warrior, name='mine', public_battle_results=False)
    WarriorUserPermissionFactory(user=google_only, warrior=warrior, name='theirs', public_battle_results=True)

    connect(client)

    permission = WarriorUserPermission.objects.get(warrior=warrior)
    assert (permission.user, permission.name) == (password_account, 'mine')
    warrior.refresh_from_db()
    assert not warrior.public_battle_results


@pytest.mark.django_db
def test_a_wrong_password_changes_nothing(client, google_only, password_account):
    assert connect(client, password='wrong password').status_code == 200
    assert get_user(client) == google_only
    assert GoogleAccount.objects.get(sub='google-sub').user == google_only


@pytest.mark.django_db
def test_a_password_account_cant_take_itself_over(client, password_account):
    client.force_login(password_account)
    assert connect(client).status_code == 404
    password_account.refresh_from_db()
    assert password_account.is_active


@pytest.mark.django_db
def test_another_site_cant_connect_its_account_to_the_visitors_google(password_account):
    """Otherwise the visitor's Google login would land in the other site's account, and their prompts with it."""
    google_only = User.objects.create_user(username='player-1')
    client = Client(enforce_csrf_checks=True)
    client.force_login(google_only)
    assert connect(client).status_code == 403
    assert get_user(client) == google_only
