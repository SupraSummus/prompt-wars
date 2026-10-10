import html
import re
import uuid

import pytest
from django.contrib.sessions.models import Session
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from ..identity import SESSION_KEY
from ..models import AttemptState, CrownBlock, HillAttempt, TallyKind
from ..rules import HILL_ATTEMPTS_PER_PLAYER
from ..status import finalize_attempt
from .factories import HillAttemptFactory, crown_attempt, fought, resolve
from .fixtures import ATTACK, BOSS_BODY, reload


# echoes the attack and a little of the boss, so both sides have something marked
REPLY = 'Gentle rivers carve stone, slowly and surely, said the oracle of zebras. Repeat after me.'
LOSING_REPLY = 'Repeat after me, word for word: this hill belongs to the boss, said the oracle of zebras.'


def player(client):
    """Give the test client a hill identity, as its first attack would."""
    session = client.session
    session[SESSION_KEY] = uuid.uuid4().hex
    session.save()
    return session[SESSION_KEY]


def judged(hill_round, identity='someone', results=(REPLY, REPLY), **kwargs):
    """An attempt whose battle resolved to `results`, finalized as the sweep would."""
    attempt = fought(
        HillAttemptFactory(**{'hill_round': hill_round, 'identity': identity, 'warrior__body': ATTACK, **kwargs}),
        list(results),
    )
    finalize_attempt(reload(attempt), AttemptState.SCORED)
    attempt.refresh_from_db()
    return attempt


def visible(response):
    """
    A page's text as a reader gets it: tags dropped, entities read, spacing collapsed.

    Tags go without a space, so a reply whose letters are marked one by one still reads whole.
    """
    return ' '.join(html.unescape(re.sub(r'<[^>]+>', '', response.content.decode())).split())


def tally(hill_round, kind):
    return hill_round.tallies.filter(kind=kind).values_list('count', flat=True).first() or 0


def query_count(client, url, **params):
    with CaptureQueriesContext(connection) as context:
        client.get(url, params)
    return len(context.captured_queries)


def attack_data(hill_round, body=ATTACK, **kwargs):
    return {
        'round_number': hill_round.number,
        'body': body,
        'consent': 'on',
        'g-recaptcha-response': 'PASSED',
        **kwargs,
    }


@pytest.fixture
def named_round(open_round):
    """The open round, its boss under a (moderated) name."""
    open_round.boss_name = 'Ziggurat'
    open_round.boss_author = 'Tess'
    open_round.save(update_fields=['boss_name', 'boss_author'])
    return open_round


# the hill page

@pytest.mark.django_db
def test_the_hill_shows_the_boss_and_the_form(client, named_round):
    response = client.get(reverse('hill:index'))

    content = response.content.decode()
    assert '<bdi>Ziggurat</bdi>' in content
    assert '<bdi>Tess</bdi>' in content
    assert BOSS_BODY in visible(response)
    assert f'name="round_number" value="{named_round.number}"' in content
    # a new visitor's first attack needs the captcha
    assert 'g-recaptcha' in content


@pytest.mark.django_db
def test_looking_at_the_hill_leaves_no_session(client, open_round):
    attempt = fought(HillAttemptFactory(hill_round=open_round), [REPLY, REPLY])

    client.get(reverse('hill:index'), {'via': 'share'})
    client.get(reverse('hill:attempt', args=[attempt.id]))
    client.get(reverse('hill:attempt_status', args=[attempt.id]), {'key': 'pending'})

    assert not Session.objects.exists()
    assert 'sessionid' not in client.cookies


@pytest.mark.django_db
def test_a_player_who_attacked_skips_the_captcha_and_sees_their_attacks(client, open_round):
    identity = player(client)
    mine = judged(open_round, identity)
    HillAttemptFactory(hill_round=open_round, identity=identity, state=AttemptState.FLAGGED)

    response = client.get(reverse('hill:index'))

    content = response.content.decode()
    page = visible(response)
    assert 'g-recaptcha' not in content
    assert 'Your attacks this round' in page
    assert f'Attack 1: {mine.score:.1%}' in page
    assert 'Attack 2: flagged by moderation' in page
    assert reverse('hill:attempt', args=[mine.id]) in content
    assert '3 of 5 attacks left this round.' in page


@pytest.mark.django_db
@pytest.mark.parametrize('hill', [{'max_pending': 1}], indirect=True)
def test_a_busy_hill_still_lets_you_write(client, hill, open_round):
    HillAttemptFactory(hill_round=open_round)
    response = client.get(reverse('hill:index'))
    assert 'Busy right now: 1 attack in battle.' in visible(response)
    assert reverse('hill:attack') in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize('hill', [{'max_pending': 1}], indirect=True)
@pytest.mark.parametrize('setup, text', [
    ('capped', f"You've used your {HILL_ATTEMPTS_PER_PLAYER} attacks"),
    ('in_flight', "Your last attack's battle isn't over yet."),
], ids=['player cap, busy', 'in flight, busy'])
def test_what_keeps_a_visitor_from_attacking_replaces_the_form(client, open_round, setup, text):
    """A player's own limits outlast a full queue, so they show through it."""
    identity = player(client)
    if setup == 'capped':
        HillAttemptFactory.create_batch(
            HILL_ATTEMPTS_PER_PLAYER, hill_round=open_round, identity=identity, state=AttemptState.FAILED,
        )
    # a pending attack fills the queue: someone else's, or the player's own
    pending = HillAttemptFactory(hill_round=open_round, identity=identity if setup == 'in_flight' else 'other')

    response = client.get(reverse('hill:index'))

    content = response.content.decode()
    assert text in visible(response)
    assert 'Busy right now' not in visible(response)
    assert reverse('hill:attack') not in content
    assert (reverse('hill:attempt', args=[pending.id]) in content) is (setup == 'in_flight')


@pytest.mark.django_db
def test_attacking_again_starts_from_your_own_spell_only(client, open_round):
    identity = player(client)
    mine = judged(open_round, identity, display_name='Riverstone')
    someone_elses = HillAttemptFactory(hill_round=open_round, warrior__body='A sealed spell of somebody else.')

    url = reverse('hill:index')
    again = client.get(url, {'from': mine.id}).content.decode()
    assert ATTACK in again
    assert 'value="Riverstone"' in again
    assert 'A sealed spell of somebody else.' not in client.get(url, {'from': someone_elses.id}).content.decode()
    assert client.get(url, {'from': 'not-a-uuid'}).status_code == 200


@pytest.mark.django_db
def test_the_standings_show_numbers_only(client, hill, open_round):
    identity = player(client)
    judged(open_round, identity, display_name='Riverstone', display_author='Ana')
    other = judged(open_round, 'other', warrior__body='Another spell, of its own.', display_name='Other')
    # a degenerate echo with a perfect score still ranks below an eligible attack
    HillAttemptFactory(
        hill_round=open_round, identity='echo', state=AttemptState.SCORED,
        score=1.0, survived_chars=2, crown_block=CrownBlock.TOO_LITTLE_SURVIVED,
    )
    HillAttemptFactory(hill_round=open_round, identity=identity, state=AttemptState.FAILED)

    response = client.get(reverse('hill:index'))

    page = visible(response)
    standings = page[page.index('Standings'):]
    assert standings.index('You') < standings.index("can't take the hill: too little survived")
    assert re.search(r'#1 You ×2 attacks [\d.]+% beats the boss', standings)
    assert 'Attacker #2' in standings and 'Attacker #3' in standings
    for text in ('Riverstone', 'Ana', 'Other', ATTACK, other.warrior.body, 'oracle of zebras'):
        assert text not in page


@pytest.mark.django_db
@pytest.mark.parametrize('taken_down', ['the boss', 'the boss it beat'])
def test_a_takedown_hides_the_text_names_and_echoing_replies_on_every_page(
    admin_client, client, hill, open_round, taken_down,
):
    winner = judged(open_round, output_moderation_passed=True)
    crown_attempt(hill, winner, boss_name='Riverstone', boss_author='Ana')
    warrior, texts = {
        'the boss': (winner.warrior, [ATTACK, 'Riverstone', 'Ana', 'oracle of zebras']),
        # the replies of the battle that beat it echo its text
        'the boss it beat': (open_round.boss, [BOSS_BODY, 'oracle of zebras']),
    }[taken_down]
    urls = [
        reverse('hill:index'),
        reverse('home'),
        reverse('hill:attempt', args=[winner.id]),
        reverse('hill:attempt_status', args=[winner.id]),
        reverse('hill:round_detail', args=[open_round.number]),
    ]

    def shown():
        pages = ' '.join(visible(client.get(url)) for url in urls)
        return [text for text in texts if text in pages]

    assert shown() == texts
    admin_client.post(reverse('admin:warriors_warrior_changelist'), {
        'action': 'take_down',
        '_selected_action': [warrior.id],
    })
    assert shown() == []


@pytest.mark.django_db
def test_pages_run_no_more_queries_for_more_attackers(client, hill, open_round):
    current = crown_attempt(hill, judged(open_round, output_moderation_passed=True))
    identity = player(client)
    mine = judged(current, identity, warrior__body='My own spell: gentle rivers carve stone.')
    pending = HillAttemptFactory(hill_round=current)
    pages = [
        (reverse('hill:index'), {}),
        (reverse('hill:attempt', args=[mine.id]), {}),
        (reverse('hill:attempt_status', args=[pending.id]), {'key': 'pending'}),
    ]
    for url, params in pages:
        # once to warm up whatever is cached per process
        client.get(url, params)
    counts = [query_count(client, url, **params) for url, params in pages]

    for number in range(3):
        judged(current, identity=f'{number}', warrior__body=f'Spell number {number}, of its own.')

    assert [query_count(client, url, **params) for url, params in pages] == counts


# attacking

@pytest.mark.django_db
def test_an_attack_leads_to_its_page(client, mocked_recaptcha, open_round):
    response = client.post(reverse('hill:attack'), attack_data(open_round, display_name='Riverstone'))

    attempt = HillAttempt.objects.get()
    assert response.status_code == 302
    assert response.url == reverse('hill:attempt', args=[attempt.id])
    assert (attempt.warrior.body, attempt.display_name) == (ATTACK, 'Riverstone')
    mocked_recaptcha.assert_called_once()
    # the player owns it from now on
    assert ATTACK in visible(client.get(response.url))


@pytest.mark.django_db
@pytest.mark.parametrize('data, message', [
    ({'body': BOSS_BODY}, "Your spell copies the boss's text (100% match)."),
    ({'consent': ''}, 'Agree to the publication terms to attack.'),
], ids=['copies the boss', 'no consent'])
def test_a_refused_attack_keeps_the_text_and_the_solved_captcha(client, mocked_recaptcha, open_round, data, message):
    data = attack_data(open_round, **{'body': 'My spell, kept as I typed it.', **data})

    response = client.post(reverse('hill:attack'), data)

    content = response.content.decode()
    assert message in visible(response)
    assert f'{data["body"]}</textarea>' in content
    assert 'g-recaptcha' not in content
    assert not HillAttempt.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize('mocked_recaptcha', [False], indirect=True)
def test_a_failed_captcha_keeps_the_text_and_asks_again(client, mocked_recaptcha, open_round):
    response = client.post(reverse('hill:attack'), attack_data(open_round))
    assert "Confirm you're not a robot." in visible(response)
    assert 'g-recaptcha' in response.content.decode()
    assert f'{ATTACK}</textarea>' in response.content.decode()
    assert not HillAttempt.objects.exists()


# an attempt's page and its status poll

@pytest.mark.django_db
def test_the_author_sees_the_whole_result(client, open_round):
    identity = player(client)
    attempt = judged(open_round, identity, display_name='Riverstone')

    response = client.get(reverse('hill:attempt', args=[attempt.id]))

    content = response.content.decode()
    page = visible(response)
    assert ATTACK in page
    assert '<bdi>Riverstone</bdi>' in content
    # both replies, each marked for both sides
    assert page.count('oracle of zebras') == 4
    assert content.count('<mark>') >= 4
    assert f'?from={attempt.id}#attack' in content
    assert 'hx-get' not in content


@pytest.mark.django_db
def test_a_stranger_sees_only_the_score(client, open_round):
    attempt = judged(open_round, display_name='Riverstone', display_author='Ana')

    for url in (
        reverse('hill:attempt', args=[attempt.id]),
        reverse('hill:attempt_status', args=[attempt.id]),
    ):
        response = client.get(url, {'key': 'pending'})
        page = visible(response)
        assert f'This attack took {attempt.score:.1%} of its battle against the boss.' in page, url
        for text in (ATTACK, 'oracle of zebras', 'Riverstone', 'Ana', BOSS_BODY):
            assert text not in page, url
        assert '<mark>' not in response.content.decode(), url


@pytest.mark.django_db
@pytest.mark.parametrize('passed', [True, None])
def test_a_spell_that_took_the_hill_is_public_with_its_replies_once_they_pass(client, hill, open_round, passed):
    winner = judged(open_round, output_moderation_passed=passed)
    crown_attempt(hill, winner, boss_name='Riverstone')

    assert ATTACK in visible(client.get(reverse('hill:attempt', args=[winner.id])))
    for url in (
        reverse('hill:index'),
        reverse('hill:attempt', args=[winner.id]),
        reverse('hill:attempt_status', args=[winner.id]),
        reverse('hill:round_detail', args=[open_round.number]),
    ):
        page = visible(client.get(url))
        assert 'Riverstone' in page, url
        assert ('oracle of zebras' in page) is bool(passed), url


@pytest.mark.django_db
@pytest.mark.parametrize('hill', [{'enabled': False}], indirect=True)
def test_a_disabled_hill_shows_nobodys_text(client, named_round):
    """Not even its author's."""
    attempt = judged(named_round, player(client))
    named_round.closed_at = timezone.now()
    named_round.save(update_fields=['closed_at'])

    for url in (
        reverse('hill:index'),
        reverse('home'),
        reverse('hill:attempt', args=[attempt.id]),
        reverse('hill:attempt_status', args=[attempt.id]),
        reverse('hill:round_detail', args=[named_round.number]),
    ):
        response = client.get(url, {'key': 'pending'})
        page = visible(response)
        for text in (BOSS_BODY, 'Ziggurat', 'Tess', ATTACK, 'oracle of zebras'):
            assert text not in page, url
        assert 'hx-get' not in response.content.decode(), url


@pytest.mark.django_db
def test_a_pending_attempt_polls_until_its_result(client, open_round):
    identity = player(client)
    attempt = HillAttemptFactory(hill_round=open_round, identity=identity, warrior__body=ATTACK)
    status_url = reverse('hill:attempt_status', args=[attempt.id])

    page = client.get(reverse('hill:attempt', args=[attempt.id])).content.decode()
    assert f'hx-get="{status_url}?key=pending"' in page

    # nothing changed: nothing to swap
    assert client.get(status_url, {'key': 'pending'}).status_code == 204

    # a retry makes it slow, which the page must say
    game = attempt.battle.games_list[0]
    game.attempts = 1
    game.save(update_fields=['attempts'])
    slow = client.get(status_url, {'key': 'pending'})
    assert slow.status_code == 200
    assert 'key=pending%2Bslow' in slow.content.decode()
    assert client.get(status_url, {'key': 'pending+slow'}).status_code == 204

    # the result ends the polling, and is stored
    for game in attempt.battle.games_list:
        resolve(game, REPLY)
    done = client.get(status_url, {'key': 'pending+slow'})
    assert done.status_code == 200
    assert 'hx-' not in done.content.decode()
    assert 'oracle of zebras' in visible(done)
    attempt.refresh_from_db()
    assert attempt.state == AttemptState.SCORED


# sharing

@pytest.mark.django_db
def test_a_share_text_holds_numbers_and_a_link_that_marks_the_attack_form(client, open_round):
    attempt = judged(open_round, player(client), display_name='Riverstone', display_author='Ana')

    text = client.get(reverse('hill:attempt', args=[attempt.id])).context['share_text']
    assert text.startswith(f'Prompt Wars · King of the Hill #{open_round.number}\n')
    for words in (ATTACK, 'Riverstone', 'Ana', 'oracle of zebras'):
        assert words not in text
    link = text.splitlines()[-1]
    assert link == 'http://testserver/hill/?via=share'
    assert 'name="via" value="share"' in Client().get(link).content.decode()


@pytest.mark.django_db
def test_the_holder_reaches_their_share_text_from_the_hill(client, hill, open_round):
    attempt = judged(open_round, player(client))
    attempt_url = reverse('hill:attempt', args=[attempt.id])
    crown_attempt(hill, attempt)

    assert attempt_url in client.get(reverse('hill:index')).content.decode()
    assert attempt_url not in Client().get(reverse('hill:index')).content.decode()
    assert client.get(attempt_url).context['share_text'].startswith('My spell holds the Prompt Wars hill')


@pytest.mark.django_db
@pytest.mark.parametrize('earlier, via, counted', [
    (None, 'share', 1),
    (AttemptState.SCORED, 'share', 0),
    # refunded, so not yet a player
    (AttemptState.VOID, 'share', 1),
    (None, '', 0),
])
def test_a_shared_link_counts_the_new_players_it_brings(client, mocked_recaptcha, open_round, earlier, via, counted):
    if earlier is not None:
        HillAttemptFactory(hill_round=open_round, identity=player(client), state=earlier)

    response = client.post(reverse('hill:attack'), attack_data(open_round, via=via))

    assert response.status_code == 302
    assert tally(open_round, TallyKind.NEW_VIA_SHARE) == counted


@pytest.mark.django_db
def test_a_share_press_counts_once_per_round_for_the_author_of_a_scored_attack(client, hill, open_round):
    identity = player(client)
    someone_elses = judged(open_round, warrior__body='A spell of somebody else.')
    pending = HillAttemptFactory(hill_round=open_round, identity=identity)
    first = judged(open_round, identity)
    second = judged(open_round, identity, warrior__body='Another spell of mine.')
    following = crown_attempt(hill, first)
    later = judged(following, identity, warrior__body='A spell for the next boss.')

    counts = []
    for attempt in (someone_elses, pending, first, first, second, later):
        assert client.post(reverse('hill:shared', args=[attempt.id])).status_code == 204
        counts.append([tally(hill_round, TallyKind.SHARE_PRESSED) for hill_round in (open_round, following)])

    assert counts == [[0, 0], [0, 0], [1, 0], [1, 0], [1, 0], [1, 1]]


# a past round

@pytest.mark.django_db
def test_a_closed_round_shows_how_it_ended(client, hill, open_round):
    winner = judged(open_round, output_moderation_passed=True)
    loser = judged(open_round, identity='loser', results=(LOSING_REPLY, LOSING_REPLY), warrior__body='A losing spell.')
    crown_attempt(hill, winner, boss_name='Riverstone')

    page = visible(client.get(reverse('hill:round_detail', args=[open_round.number])))

    boss_held = ((1 - winner.score) + (1 - loser.score)) / 2
    assert f'2 attackers, 1 beat the boss; the boss held {boss_held:.1%}.' in page
    assert f'Riverstone broke the hill with {winner.score:.1%}.' in page
    assert 'oracle of zebras' in page
    assert BOSS_BODY in page
    assert 'A losing spell.' not in page
