import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from warriors.warriors import Warrior

from ..models import BossReason, Hill, HillAttempt, HouseBoss, Round
from .factories import HillAttemptFactory


def hill_crown(*args):
    call_command('hill_crown', *map(str, args))


@pytest.fixture
def body_file(tmp_path):
    path = tmp_path / 'prompt.txt'
    path.write_text('Sing the river song, verse by verse.\n', encoding='utf-8')
    return path


@pytest.mark.django_db
def test_seeding_creates_a_disabled_hill_and_its_first_round(moderation, body_file):
    before = timezone.now()

    hill_crown('--body-file', body_file, '--now', '--name', 'River song', '--author', 'Owner')

    hill = Hill.current()
    assert not hill.enabled
    (hill_round,) = hill.rounds.all()
    assert (hill_round.number, hill_round.boss_reason, hill_round.reign_round) == (1, BossReason.OWNER, 1)
    assert (hill_round.boss_name, hill_round.boss_author, hill_round.boss_attempt) == ('River song', 'Owner', None)
    assert before <= hill_round.starts_at <= timezone.now()
    assert hill_round.llm == hill.llm
    boss = hill_round.boss
    # the file's final line break is not part of the prompt
    assert boss.body == 'Sing the river song, verse by verse.'
    assert (boss.name, boss.created_by, boss.moderation_passed) == ('', None, True)
    assert moderation.calls == [[boss.body]]


@pytest.mark.django_db
def test_crowning_now_mid_round_closes_it(moderation, open_round, body_file):
    straggler = HillAttemptFactory(hill_round=open_round)
    now = timezone.now()

    hill_crown('--body-file', body_file, '--now', '--name', 'River song')

    open_round.refresh_from_db()
    assert open_round.closed_at >= now
    following = Round.objects.get(closed_at=None)
    assert (following.number, following.boss.body, following.boss_reason, following.boss_name) == (
        open_round.number + 1, 'Sing the river song, verse by verse.', BossReason.OWNER, 'River song',
    )
    assert following.starts_at >= now
    assert HillAttempt.objects.get(id=straggler.id).late


@pytest.mark.django_db
def test_a_house_boss_keeps_its_names_when_crowned_or_added_again_without_them(moderation, hill, body_file):
    hill_crown('--body-file', body_file, '--house', '--name', 'River song')
    hill_crown('--body-file', body_file, '--house', '--author', 'Owner')
    assert HouseBoss.objects.values_list('name', 'author').get() == ('River song', 'Owner')
    assert not Round.objects.exists()

    hill_crown('--body-file', body_file, '--house', '--now')
    assert HouseBoss.objects.values_list('name', 'author').get() == ('River song', 'Owner')
    following = Round.objects.get(closed_at=None)
    assert (following.boss_name, following.boss_author) == ('River song', 'Owner')

    # a name given for this crown alone leaves the stored ones alone
    hill_crown('--body-file', body_file, '--now', '--author', 'Guest')
    following = Round.objects.get(closed_at=None)
    assert (following.boss_name, following.boss_author) == ('River song', 'Guest')
    assert HouseBoss.objects.values_list('name', 'author').get() == ('River song', 'Owner')


@pytest.mark.django_db
def test_a_flagged_prompt_is_refused(moderation, body_file):
    moderation.flagged.add('Sing the river song, verse by verse.')
    with pytest.raises(CommandError, match='flagged'):
        hill_crown('--body-file', body_file, '--now')
    assert not Round.objects.exists()
    assert Warrior.objects.get().moderation_passed is False
