import base64
import hashlib
import json
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.auth import get_user
from django.urls import reverse
from google.auth import crypt, jwt

from warriors.models import WarriorUserPermission

from ..google_login import TOKEN_ENDPOINT
from ..models import GoogleAccount, User
from .factories import UserFactory
from .test_views import authorize_in_session


CLIENT_ID = 'test-client-id.apps.googleusercontent.com'


def make_signer():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    public_pem = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    return crypt.RSASigner.from_string(private_pem, 'google-key'), public_pem.decode()


@pytest.fixture
def google(settings, monkeypatch):
    """Google login switched on, with Google's signing key one the test holds; returns its signer."""
    settings.GOOGLE_OAUTH_CLIENT_ID = CLIENT_ID
    settings.GOOGLE_OAUTH_CLIENT_SECRET = 'test-secret'
    signer, public_pem = make_signer()
    certs = json.dumps({'google-key': public_pem}).encode()

    def fetch(url, method='GET', **kwargs):  # google-auth's transport interface
        return SimpleNamespace(status=200, headers={}, data=certs)

    monkeypatch.setattr('users.google_login.certs_transport', lambda: fetch)
    return signer


def signed_token(signer, **claims):
    now = int(time.time())
    return jwt.encode(signer, {
        'iss': 'https://accounts.google.com',
        'aud': CLIENT_ID,
        'sub': 'google-sub',
        'iat': now,
        'exp': now + 3600,
        **claims,
    }).decode()


def start(client, next_url=''):
    """Press the Google button; return the query of the URL it sends the visitor to."""
    response = client.post(reverse('google_login:start'), {'next': next_url})
    return {key: value for key, (value,) in parse_qs(urlsplit(response.url).query).items()}


def come_back(client, query, **token_response):
    """Return from Google's page with `query`, Google answering the code exchange with `token_response`."""
    with respx.mock:
        route = respx.post(TOKEN_ENDPOINT).respond(**token_response)
        response = client.get(reverse('google_login:callback'), query)
    return response, route


def log_in_with_google(client, token, next_url=''):
    asked = start(client, next_url)
    response, _ = come_back(client, {'state': asked['state'], 'code': 'the-code'}, json={'id_token': token})
    return response


@pytest.mark.django_db
def test_off_unless_both_keys_are_set(client, user, settings):
    settings.GOOGLE_OAUTH_CLIENT_ID = CLIENT_ID
    settings.GOOGLE_OAUTH_CLIENT_SECRET = ''
    assert 'Continue with Google' not in client.get(reverse('login')).content.decode()
    assert 'Continue with Google' not in client.get(reverse('signup')).content.decode()
    assert client.post(reverse('google_login:start')).status_code == 404
    assert client.get(reverse('google_login:callback')).status_code == 404
    client.force_login(user)
    assert 'Connect Google' not in client.get(reverse('my_warriors:index')).content.decode()


@pytest.mark.django_db
def test_login_and_signup_offer_google(client, google):
    assert 'Continue with Google' in client.get(reverse('login')).content.decode()
    assert 'Continue with Google' in client.get(reverse('signup')).content.decode()


@pytest.mark.django_db
def test_both_legs_agree_as_google_checks(client, google):
    """Google compares the redirect URI across the two legs and the verifier against the challenge."""
    asked = start(client)
    _, route = come_back(client, {'state': asked['state'], 'code': 'the-code'}, json={'id_token': signed_token(google)})
    sent = {key: value for key, (value,) in parse_qs(route.calls.last.request.content.decode()).items()}
    assert asked['redirect_uri'] == sent['redirect_uri'] == 'http://testserver/login/google/callback/'
    assert asked['client_id'] == sent['client_id'] == CLIENT_ID
    assert asked['code_challenge'] == base64.urlsafe_b64encode(
        hashlib.sha256(sent['code_verifier'].encode()).digest(),
    ).rstrip(b'=').decode()
    assert asked['code_challenge_method'] == 'S256'
    assert sent['code'] == 'the-code'
    assert sent['client_secret'] == 'test-secret'


@pytest.mark.django_db
def test_first_login_makes_an_account_that_keeps_the_browsers_prompts(client, google, warrior):
    authorize_in_session(client, warrior)
    log_in_with_google(client, signed_token(google, sub='new-sub'))
    user = get_user(client)
    assert GoogleAccount.objects.get(sub='new-sub').user == user
    assert not user.has_usable_password()
    assert list(WarriorUserPermission.objects.filter(user=user).values_list('warrior', flat=True)) == [warrior.id]


@pytest.mark.django_db
def test_returning_login_logs_in_the_same_account(client, google, user):
    GoogleAccount.objects.create(sub='known-sub', user=user)
    log_in_with_google(client, signed_token(google, sub='known-sub'))
    assert get_user(client) == user
    assert User.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(('next_url', 'lands_on'), [
    ('/leaderboard/', '/leaderboard/'),
    ('https://example.org/', '/'),  # not off the site
])
def test_login_goes_where_the_visitor_was_headed(client, google, next_url, lands_on):
    assert log_in_with_google(client, signed_token(google), next_url).url == lands_on


@pytest.mark.django_db
def test_my_prompts_offers_connecting_until_connected(user_client, user, google):
    assert 'Connect Google' in user_client.get(reverse('my_warriors:index')).content.decode()
    GoogleAccount.objects.create(sub='known-sub', user=user)
    assert 'Connect Google' not in user_client.get(reverse('my_warriors:index')).content.decode()


@pytest.mark.django_db
def test_logged_in_visitor_connects_google_to_their_account(user_client, user, google):
    log_in_with_google(user_client, signed_token(google, sub='new-sub'))
    assert GoogleAccount.objects.get(sub='new-sub').user == user
    assert get_user(user_client) == user
    assert User.objects.count() == 1


@pytest.mark.django_db
def test_connecting_leaves_a_google_account_of_another_user_be(user_client, user, google):
    other_user = UserFactory()
    GoogleAccount.objects.create(sub='taken-sub', user=other_user)
    log_in_with_google(user_client, signed_token(google, sub='taken-sub'))
    assert GoogleAccount.objects.get(sub='taken-sub').user == other_user
    assert get_user(user_client) == user


@pytest.mark.django_db
def test_refuses_a_token_issued_to_another_client(client, google):
    log_in_with_google(client, signed_token(google, aud='another-client-id'))
    assert not get_user(client).is_authenticated


@pytest.mark.django_db
def test_refuses_a_token_signed_by_another_key(client, google):
    other_signer, _ = make_signer()
    log_in_with_google(client, signed_token(other_signer))
    assert not get_user(client).is_authenticated


@pytest.mark.django_db
def test_refuses_when_google_turns_down_the_code(client, google):
    asked = start(client)
    come_back(client, {'state': asked['state'], 'code': 'the-code'}, status_code=400, json={'error': 'invalid_grant'})
    assert not get_user(client).is_authenticated


@pytest.mark.django_db
def test_refuses_an_answer_this_session_did_not_ask_for(client, google):
    start(client)
    _, route = come_back(client, {'state': 'forged', 'code': 'the-code'}, json={'id_token': signed_token(google)})
    assert not route.called
    assert not get_user(client).is_authenticated


@pytest.mark.django_db
def test_an_answer_is_good_once(client, google):
    asked = start(client)
    answer = {'state': asked['state'], 'code': 'the-code'}
    come_back(client, answer, json={'id_token': signed_token(google)})
    _, route = come_back(client, answer, json={'id_token': signed_token(google)})
    assert not route.called


@pytest.mark.django_db
def test_declining_on_googles_page_logs_in_nobody(client, google):
    asked = start(client)
    response = client.get(reverse('google_login:callback'), {'state': asked['state'], 'error': 'access_denied'})
    assert response.url.startswith(reverse('login'))
    assert not get_user(client).is_authenticated


@pytest.mark.django_db
def test_disabled_account_stays_out(client, google):
    GoogleAccount.objects.create(sub='known-sub', user=UserFactory(is_active=False))
    response = log_in_with_google(client, signed_token(google, sub='known-sub'))
    assert response.url.startswith(reverse('login'))
