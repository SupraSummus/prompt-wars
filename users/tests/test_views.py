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
