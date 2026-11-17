import pytest
from django.urls import reverse
from django_goals.models import Goal

from .models import WarriorUserPermission
from .rankings import Ranking
from .warriors import MAX_WARRIOR_LENGTH, Warrior


@pytest.mark.django_db
def test_create_warrior_get(client):
    response = client.get(reverse('warrior_create'))
    assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize('has_authorized_warriors', [True, False])
def test_create_warrior(client, mocked_recaptcha, has_authorized_warriors):
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
    warrior = Warrior.objects.get(id=warrior_id)
    assert warrior.name == 'Test Warrior'
    assert warrior.author_name == 'Test Author'
    assert warrior.body == 'Test Body'
    assert len(warrior.body_sha_256) == 32
    assert warrior.moderation_date is None
    # entered for the ladder: its clock runs, and it stands on every leaderboard
    assert warrior.next_battle_schedule is not None
    assert {
        (rating.ranking, rating.rating, rating.games_played)
        for rating in warrior.ratings.all()
    } == {(ranking.value, 0.0, 0) for ranking in Ranking}

    # moderation task scheduled
    goal = Goal.objects.get()
    assert goal.handler == 'warriors.tasks.do_moderation'
    assert goal.instructions['args'] == [str(warrior.id)]

    # session is athorized for new warrior
    assert str(warrior.id) in response.client.session['authorized_warriors']


@pytest.mark.django_db
def test_create_warrior_enters_a_hill_warrior_for_the_ladder(client, mocked_recaptcha, warrior):
    """Submitting the text of a warrior that played only the hill starts its ladder clock."""
    warrior.next_battle_schedule = None
    warrior.save(update_fields=['next_battle_schedule'])
    response = client.post(
        reverse('warrior_create'),
        data={
            'body': warrior.body,
            'g-recaptcha-response': 'PASSED',
        },
    )
    assert response.status_code == 302
    warrior.refresh_from_db()
    assert warrior.next_battle_schedule is not None
    assert warrior.ratings.count() == len(Ranking)


@pytest.mark.django_db
def test_create_warrior_duplicate(client, warrior, mocked_recaptcha):
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
def test_create_no_strip(client, mocked_recaptcha):
    response = client.post(
        reverse('warrior_create'),
        data={
            'body': ' Test \r\nWarrior \n\n',
            'g-recaptcha-response': 'PASSED',
        },
    )
    assert response.status_code == 302
    warrior = Warrior.objects.get()
    assert warrior.body == ' Test \nWarrior \n\n'


@pytest.mark.django_db
@pytest.mark.parametrize(
    ('length', 'expect_success'),
    [
        (MAX_WARRIOR_LENGTH, True),
        (MAX_WARRIOR_LENGTH + 1, False),
    ],
)
def test_create_crlf_length(client, mocked_recaptcha, length, expect_success):
    response = client.post(
        reverse('warrior_create'),
        data={
            'body': '\r\n' * length,
            'g-recaptcha-response': 'PASSED',
        },
    )
    if expect_success:
        assert response.status_code == 302
        warrior = Warrior.objects.get()
        assert warrior.body == '\n' * length
    else:
        assert response.status_code == 200
        assert response.context['form'].errors['body']


@pytest.mark.django_db
def test_create_length_reported(client, mocked_recaptcha):
    response = client.post(
        reverse('warrior_create'),
        data={
            'body': 'a' * (MAX_WARRIOR_LENGTH + 123),
            'g-recaptcha-response': 'PASSED',
        },
    )
    assert response.status_code == 200
    assert str(MAX_WARRIOR_LENGTH + 123) in response.context['form'].errors['body'][0]


@pytest.mark.django_db
def test_create_authenticated(user, user_client, mocked_recaptcha):
    response = user_client.post(
        reverse('warrior_create'),
        data={
            'body': 'Test Warrior',
            'g-recaptcha-response': 'PASSED',
        },
    )
    assert response.status_code == 302
    warrior = Warrior.objects.get()
    assert warrior.created_by == user
    assert user in warrior.users.all()


@pytest.mark.django_db
@pytest.mark.parametrize('warrior', [{
    'name': 'strongest',
    'public_battle_results': False,
}], indirect=True)
def test_create_authenticated_duplicate(
    user, user_client,
    warrior,
    mocked_recaptcha,
):
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
        warrior=warrior,
        user=user,
    )
    assert warrior_user_permission.name == 'surely a duplicate'
