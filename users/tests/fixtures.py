import json
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from google.auth import crypt

from .factories import UserFactory


@pytest.fixture
def user(request):
    return UserFactory(
        **getattr(request, 'param', {}),
    )


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
