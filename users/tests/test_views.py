import pytest
from django.urls import reverse

from warriors.models import WarriorUserPermission

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


def signup_data(**extra):
    return {
        'username': 'testuser',
        'password1': 'a long and unusual password',
        'password2': 'a long and unusual password',
        'g-recaptcha-response': 'PASSED',
        **extra,
    }


def authorize_in_session(client, *warriors):
    session = client.session
    session['authorized_warriors'] = [str(warrior.id) for warrior in warriors]
    session.save()


@pytest.mark.django_db
def test_signup_logs_in_and_keeps_the_browsers_prompts(client, mocked_recaptcha, warrior):
    authorize_in_session(client, warrior)
    response = client.post(reverse('signup'), signup_data())
    assert response.status_code == 302, response.context['form'].errors
    assert response.url == reverse('home')
    user = User.objects.get()
    assert client.session['_auth_user_id'] == str(user.id)
    assert list(WarriorUserPermission.objects.filter(user=user).values_list('warrior', flat=True)) == [warrior.id]


@pytest.mark.django_db
@pytest.mark.parametrize(('next_url', 'lands_on'), [
    ('/leaderboard/', '/leaderboard/'),
    ('https://example.org/', '/'),  # not off the site
])
def test_signup_goes_where_the_visitor_was_headed(client, mocked_recaptcha, next_url, lands_on):
    response = client.post(reverse('signup'), signup_data(next=next_url))
    assert response.status_code == 302
    assert response.url == lands_on


@pytest.mark.django_db
def test_login_keeps_the_browsers_prompts(client, user, warrior, other_warrior):
    user.set_password('secret password')
    user.save()
    # one the account already has, which logging in leaves be
    WarriorUserPermission.objects.create(warrior=other_warrior, user=user, name='kept name')
    authorize_in_session(client, warrior, other_warrior)
    response = client.post(reverse('login'), {'username': user.username, 'password': 'secret password'})
    assert response.status_code == 302
    assert response.url == reverse('home')
    permissions = WarriorUserPermission.objects.filter(user=user)
    assert {permission.warrior_id for permission in permissions} == {warrior.id, other_warrior.id}
    assert permissions.get(warrior=other_warrior).name == 'kept name'
