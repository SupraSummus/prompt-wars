import pytest
from django.urls import reverse

from ..models import User


@pytest.mark.django_db
def test_signup(client, mocked_recaptcha):
    url = reverse('signup')
    data = {
        'username': 'testuser',
        'password1': 'testpassword',
        'password2': 'testpassword',
        'g-recaptcha-response': 'PASSED',
    }
    response = client.post(url, data)
    assert response.status_code == 302, response.context['form'].errors
    assert User.objects.count() == 1
    user = User.objects.get()
    assert user.username == 'testuser'
    assert user.check_password('testpassword')
    assert user.is_active
    assert not user.is_staff
    assert not user.is_superuser


@pytest.mark.django_db
def test_logout_requires_post(client, user):
    """Test that logout requires POST request (not GET)."""
    client.force_login(user)
    url = reverse('logout')
    
    # GET request should return 405 Method Not Allowed
    response = client.get(url)
    assert response.status_code == 405
    
    # User should still be authenticated after GET
    assert '_auth_user_id' in client.session


@pytest.mark.django_db
def test_logout_with_post(client, user):
    """Test that logout works with POST request."""
    client.force_login(user)
    url = reverse('logout')
    
    # POST request should logout successfully
    response = client.post(url)
    assert response.status_code == 302  # Redirect after logout
    
    # User should no longer be authenticated
    assert '_auth_user_id' not in client.session
