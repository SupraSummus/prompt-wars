import pytest
from django.urls import reverse
from django_goals.models import Goal

from .models import MAX_WARRIOR_LENGTH, WarriorArena, WarriorUserPermission


@pytest.mark.django_db
def test_create_warrior_get(client, default_arena):
    response = client.get(reverse('warrior_create'))
    assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize('has_authorized_warriors', [True, False])
def test_create_warrior(client, mocked_recaptcha, has_authorized_warriors, default_arena):
    if has_authorized_warriors:
        session = client.session
        session['authorized_warriors'] = []
        session.save()
    response = client.post(
        reverse('warrior_create'),
        data={
            'name': 'Test Warrior',
            'author_name': 'Test Author',
            'body': 'Test Body',
            'g-recaptcha-response': 'PASSED',
        },
    )
    assert response.status_code == 302, response.context['form'].errors
    path = response.url
    warrior_id = path.split('/')[-2]

    # right database state
    warrior = WarriorArena.objects.get(id=warrior_id)
    assert warrior.arena == default_arena
    assert warrior.name == 'Test Warrior'
    assert warrior.author_name == 'Test Author'
    assert warrior.body == 'Test Body'
    assert len(warrior.body_sha_256) == 32
    assert warrior.rating == 0.0
    assert warrior.games_played == 0
    assert warrior.moderation_date is None

    # moderation task scheduled
    goal = Goal.objects.get()
    assert goal.handler == 'warriors.tasks.do_moderation'
    assert goal.instructions['args'] == [str(warrior.id)]

    # session is athorized for new warrior
    assert str(warrior.id) in response.client.session['authorized_warriors']


@pytest.mark.django_db
def test_create_warrior_arena(client, mocked_recaptcha, arena):
    response = client.post(
        reverse('arena_warrior_create', args=(arena.id,)),
        data={
            'body': 'Test Warrior',
            'g-recaptcha-response': 'PASSED',
        },
    )
    assert response.status_code == 302
    warrior = WarriorArena.objects.get()
    assert warrior.arena == arena


@pytest.mark.django_db
def test_create_warrior_duplicate(client, warrior, mocked_recaptcha, default_arena):
    """
    It is not possible to create a warrior that has the same body as another.
    But we have a "discover" mechanics.
    """
    response = client.post(
        reverse('warrior_create'),
        data={
            'body': warrior.body,
            'g-recaptcha-response': 'PASSED',
        },
    )
    assert response.status_code == 302
    warrior_id = response.url.split('/')[-2]
    assert warrior_id == str(warrior.id)
    assert str(warrior.id) in response.client.session['authorized_warriors']


@pytest.mark.django_db
def test_create_no_strip(client, mocked_recaptcha, default_arena):
    response = client.post(
        reverse('warrior_create'),
        data={
            'body': ' Test \r\nWarrior \n\n',
            'g-recaptcha-response': 'PASSED',
        },
    )
    assert response.status_code == 302
    warrior = WarriorArena.objects.get()
    assert warrior.body == ' Test \nWarrior \n\n'


@pytest.mark.django_db
@pytest.mark.parametrize(
    ('length', 'expect_success'),
    [
        (MAX_WARRIOR_LENGTH, True),
        (MAX_WARRIOR_LENGTH + 1, False),
    ],
)
def test_create_crlf_length(client, mocked_recaptcha, default_arena, length, expect_success):
    response = client.post(
        reverse('warrior_create'),
        data={
            'body': '\r\n' * length,
            'g-recaptcha-response': 'PASSED',
        },
    )
    if expect_success:
        assert response.status_code == 302
        warrior = WarriorArena.objects.get()
        assert warrior.body == '\n' * length
    else:
        assert response.status_code == 200
        assert response.context['form'].errors['body']


@pytest.mark.django_db
def test_create_authenticated(user, user_client, mocked_recaptcha, default_arena):
    response = user_client.post(
        reverse('warrior_create'),
        data={
            'body': 'Test Warrior',
            'g-recaptcha-response': 'PASSED',
        },
    )
    assert response.status_code == 302
    warrior = WarriorArena.objects.get()
    assert warrior.created_by == user
    assert user in warrior.users.all()


@pytest.mark.django_db
@pytest.mark.parametrize('warrior', [{
    'name': 'strongest',
    'public_battle_results': False,
}], indirect=True)
def test_create_authenticated_duplicate(user, user_client, warrior, mocked_recaptcha, default_arena):
    response = user_client.post(
        reverse('warrior_create'),
        data={
            'body': warrior.body,
            'name': 'surely a duplicate',
            'public_battle_results': True,
            'g-recaptcha-response': 'PASSED',
        },
    )
    assert response.status_code == 302
    warrior_id = response.url.split('/')[-2]
    assert warrior_id == str(warrior.id)

    # name is not changed
    warrior.refresh_from_db()
    assert warrior.name == 'strongest'

    # at least one user marked battles as public, so the warrior have public battles
    assert warrior.public_battle_results is True

    # user has access to the warrior
    warrior_user_permission = WarriorUserPermission.objects.get(
        warrior_arena=warrior,
        user=user,
    )
    assert warrior_user_permission.name == 'surely a duplicate'