"""
Log in with Google: OpenID Connect's authorization code flow,
with `google-auth` checking the ID token (`docs/accounts.md` says why no framework).

It is on when `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET` are both set,
so a deploy without them serves the password login alone.
They come from a Google Cloud OAuth client of the "Web application" type,
whose authorized redirect URI is `https://<host>/login/google/callback/`.
"""
import base64
import hashlib
import logging
import secrets
from urllib.parse import urlencode

import google.auth.exceptions
import google.auth.transport.requests
import httpx
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, resolve_url
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from google.oauth2 import id_token

from djsfc import Router

from .models import GoogleAccount, User


logger = logging.getLogger(__name__)

router = Router(__name__)

AUTHORIZATION_ENDPOINT = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_ENDPOINT = 'https://oauth2.googleapis.com/token'
TOKEN_TIMEOUT_SECONDS = 10
# how far our clock may be off Google's when checking the token's `iat` and `exp`
CLOCK_SKEW_SECONDS = 10

# one login's state between leaving for Google and coming back
SESSION_KEY = 'google_login'


def is_enabled():
    return bool(settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET)


@router.route('POST', '')
def start(request):
    """
    Send the visitor to Google.
    A POST, so another site can't start a login in the visitor's browser;
    `state` ties Google's answer to this session, and PKCE ties the code to this request.
    """
    if not is_enabled():
        raise Http404
    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    request.session[SESSION_KEY] = {
        'state': state,
        'code_verifier': code_verifier,
        'next': safe_next(request, request.POST.get('next')),
    }
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest(),
    ).rstrip(b'=').decode()
    return redirect(AUTHORIZATION_ENDPOINT + '?' + urlencode({
        'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
        'redirect_uri': callback_url(request),
        'response_type': 'code',
        'scope': 'openid',
        'state': state,
        'code_challenge': code_challenge,
        'code_challenge_method': 'S256',
    }))


@router.route('GET', 'callback/')
def callback(request):
    """
    Where Google sends the visitor back: log in as the Google account's user,
    making one for an account seen the first time,
    or connect the Google account to the visitor's if they are logged in.
    """
    if not is_enabled():
        raise Http404
    flow = request.session.pop(SESSION_KEY, None)
    if flow is None or not secrets.compare_digest(request.GET.get('state', ''), flow['state']):
        return fail(request, "That Google login has expired. Please try again.", resolve_url(settings.LOGIN_REDIRECT_URL))
    if 'code' not in request.GET:
        # the visitor declined on Google's page
        return fail(request, "Google login was cancelled.", flow['next'])
    sub = fetch_subject(request, request.GET['code'], flow['code_verifier'])
    if sub is None:
        return fail(request, "Google login failed. Please try again.", flow['next'])

    google_account = GoogleAccount.objects.filter(sub=sub).select_related('user').first()
    if request.user.is_authenticated:
        if google_account is None:
            GoogleAccount.objects.create(sub=sub, user=request.user)
            messages.success(request, "Google account connected: you can log in with it from now on.")
        elif google_account.user_id != request.user.id:
            # the two accounts would have to merge (`docs/accounts.md`), and this counts who needs it
            logger.warning('Google login: user %s tried to connect the Google account of user %s', request.user.id, google_account.user_id)
            messages.error(request, "That Google account logs in to another account here, so it can't be connected to this one.")
        return redirect(flow['next'])

    if google_account is None:
        with transaction.atomic():
            # no password: the account logs in with Google only
            user = User.objects.create_user(username=f'spellcaster-{secrets.token_hex(4)}')
            GoogleAccount.objects.create(sub=sub, user=user)
    else:
        user = google_account.user
    if not user.is_active:
        return fail(request, "This account is disabled.", flow['next'])
    login(request, user)
    return redirect(flow['next'])


def fetch_subject(request, code, code_verifier):
    """
    Trade the code for an ID token and return the Google account's subject id,
    or None when Google or the token says no.
    """
    try:
        response = httpx.post(TOKEN_ENDPOINT, data={
            'code': code,
            'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
            'client_secret': settings.GOOGLE_OAUTH_CLIENT_SECRET,
            'redirect_uri': callback_url(request),
            'grant_type': 'authorization_code',
            'code_verifier': code_verifier,
        }, timeout=TOKEN_TIMEOUT_SECONDS)
        response.raise_for_status()
        claims = id_token.verify_oauth2_token(
            response.json()['id_token'],
            certs_transport(),
            audience=settings.GOOGLE_OAUTH_CLIENT_ID,
            clock_skew_in_seconds=CLOCK_SKEW_SECONDS,
        )
    except (httpx.HTTPError, KeyError, ValueError, google.auth.exceptions.GoogleAuthError):
        # a misconfigured client lands here on every login, which is worth an alert
        logger.exception('Google login failed')
        return None
    return claims['sub']


def certs_transport():
    """What fetches Google's signing keys for `verify_oauth2_token`; tests swap it for a fake."""
    return google.auth.transport.requests.Request()


def callback_url(request):
    # the same in both legs, as Google requires; `SECURE_PROXY_SSL_HEADER` makes it https
    return request.build_absolute_uri(reverse('google_login:callback'))


def safe_next(request, url):
    if url and url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return url
    return resolve_url(settings.LOGIN_REDIRECT_URL)


def fail(request, message, next_url):
    messages.error(request, message)
    if request.user.is_authenticated:
        return redirect(next_url)
    return redirect(reverse('login') + '?' + urlencode({'next': next_url}))
