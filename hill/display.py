"""
What the hill's pages show, put together from the rules and the rows.

The views decide what a viewer may see (`hill.rules.is_public`);
this builds the numbers, labels and share text for it.
A name someone typed reaches another viewer only through `Round.shown_name` and `shown_author`,
and the meta tags, which link previews show to anyone, carry numbers only.
"""
from django.utils import timezone

from warriors.lcs import lcs_len
from warriors.score import ScoreAlgorithm

from .models import AttemptState, BossReason, Hill, Round
from .rules import HILL_MAX_REIGN_ROUNDS, beats_boss, standings


# Rows the standings list; a viewer below them sees their own row added at the end.
HILL_STANDINGS_SIZE = 20
# Squares in a share text's bar: one per tenth, enough to read at a glance in a post.
SHARE_BAR_SQUARES = 10


def percent1(value):
    """A share as a percentage to one decimal, fine enough to tell close attacks apart; `|percentage:1` in templates."""
    return f'{value:.1%}'


def _plural(count, word):
    return f'{count} {word}' if count == 1 else f'{count} {word}s'


def shown_state(attempt, state):
    """
    `state` as a page shows it for `attempt`:
    a scored attempt whose prompt has since been flagged by moderation reads as flagged,
    before the sweep gets to storing that.
    """
    if state == AttemptState.SCORED and attempt.warrior.moderation_passed is False:
        return AttemptState.FLAGGED
    return state


def reign_line(hill_round):
    """How a round's boss came to hold the hill, for its card; no names, which the card shows itself."""
    if hill_round.reign_round > 1:
        since = hill_round.number - hill_round.reign_round + 1
        # past its term, a boss holds only for want of a successor, so there is no "of" to count to
        term = f' of {HILL_MAX_REIGN_ROUNDS}' if hill_round.reign_round <= HILL_MAX_REIGN_ROUNDS else ''
        return f'Holding since Hill #{since} (round {hill_round.reign_round}{term}).'
    if hill_round.boss_reason == BossReason.BROKE:
        return f'Broke the hill with {percent1(hill_round.boss_attempt.score)}.'
    if hill_round.boss_reason == BossReason.INHERITED:
        return "Inherited the hill as the best attack of the last boss's reign."
    if hill_round.boss_reason == BossReason.HOUSE:
        return 'A house boss, stepping in.'
    return 'Put on the hill by its keeper.'


def battle_view(attempt, *, attacker_label, boss_label, replies, attacker_prompt_label=None):
    """
    An attempt's scored battle, from the attacker's side: its score, then each game.

    `replies` says whether the replies are shown, marked with what survived;
    the numbers are shown either way, survival among them:
    characters kept in order (`lcs_len`), which a game's score, relative to the other prompt, doesn't say.
    `attacker_prompt_label` names the attacker's prompt where its label can't ("your prompt" for "You").
    """
    attacker = attempt.warrior
    boss = attempt.hill_round.boss
    games = []
    for game in attempt.battle.games_list:
        result = game.result
        score = game.score_object(ScoreAlgorithm.LCS).score_for(attacker.id)
        games.append({
            'attacker_first': game.warrior_1_id == attacker.id,
            'score': score,
            'boss_score': 1 - score,
            'reply_length': len(result),
            'attacker_survived': lcs_len(attacker.body, result),
            'attacker_length': len(attacker.body),
            'boss_survived': lcs_len(boss.body, result),
            'boss_length': len(boss.body),
            'result': result if replies else '',
            'attacker_marked': game.result_marked_for(attacker) if replies and result else None,
            'boss_marked': game.result_marked_for(boss) if replies and result else None,
        })
    games.sort(key=lambda game: not game['attacker_first'])
    return {
        'attempt': attempt,
        'score': attempt.score,
        'boss_score': 1 - attempt.score,
        'games': games,
        'replies': replies,
        'attacker_label': attacker_label,
        'attacker_prompt_label': attacker_prompt_label or attacker_label,
        'boss_label': boss_label,
    }


def share_bar(share):
    filled = round(share * SHARE_BAR_SQUARES)
    return '🟩' * filled + '⬜' * (SHARE_BAR_SQUARES - filled)


def share_text(battle, hill_round, url, holding_round=None):
    """
    A post about a result: numbers and emoji bars, and the hill's address.

    Never the prompt or its names, which stay the author's to share;
    `holding_round` is the round the attempt's prompt holds the hill in, if it does.
    """
    if holding_round is not None:
        return (
            f'My prompt holds the Prompt Wars hill (#{holding_round.number}). Can you break it?\n'
            f'{url}'
        )
    first, second = (game['score'] for game in battle['games'])
    return '\n'.join([
        f'Prompt Wars · King of the Hill #{hill_round.number}',
        f'I took {percent1(first)} going first, {percent1(second)} going second against the boss.',
        share_bar(first),
        share_bar(second),
        url,
    ])


def _standing_row(row, identity):
    attempt = row.attempt
    return {
        'rank': row.rank,
        'you': attempt.identity == identity,
        'attacker_number': row.attacker_number,
        'attempt_count': row.attempt_count,
        'score': attempt.score,
        'crown_block': attempt.get_crown_block_display() if attempt.crown_block else '',
        'beats_the_boss': beats_boss(attempt),
    }


def standing_rows(rows, identity):
    """
    The standings `rows` as a page lists them: the top ones, then the viewer's own if it is lower.

    Numbers only, and "You" or "Attacker #k" for a handle:
    while a round is open, nobody's prompt or names are shown.
    """
    shown = [_standing_row(row, identity) for row in rows[:HILL_STANDINGS_SIZE]]
    own = next((
        _standing_row(row, identity)
        for row in rows[HILL_STANDINGS_SIZE:]
        if row.attempt.identity == identity
    ), None)
    return {
        'rows': shown,
        'own': own,
        'total': len(rows),
    }


def standing_of(hill_round, identity):
    """The identity's row of the round's standings, and the number of rows; None for the row if it has none."""
    rows = standings(hill_round)
    own = next((row for row in rows if row.attempt.identity == identity), None)
    return own, len(rows)


def index_meta(hill_round, stats):
    if not stats['attackers']:
        attacks = 'Nobody has attacked the boss yet.'
    else:
        attacks = (
            f"{_plural(stats['attackers'], 'player')} attacked the boss; "
            f"{stats['broke_through']} beat it."
        )
    return {
        'meta_title': f'King of the Hill #{hill_round.number}',
        'meta_description': f'{attacks} Write a prompt that takes the hill.',
    }


def attempt_meta(attempt, state):
    """An attempt's link preview: its score once it has one to show (`state`, as `shown_state` gives it)."""
    number = attempt.hill_round.number
    if state != AttemptState.SCORED:
        description = f"An attack on the Hill #{number} boss on Prompt Wars."
    else:
        description = f'This prompt took {percent1(attempt.score)} of its battle against the Hill #{number} boss.'
    return {
        'meta_title': f'An attack on Hill #{number}',
        'meta_description': description,
    }


def round_meta(hill_round, stats):
    return {
        'meta_title': f'Hill #{hill_round.number} results',
        'meta_description': (
            f'Hill #{hill_round.number} results: '
            f"{_plural(stats['attackers'], 'attacker')}, {stats['broke_through']} beat the boss."
        ),
    }


def home_card():
    """The hill's card for the home page: its open round and live numbers; None when the hill is off."""
    hill = Hill.current()
    if hill is None or not hill.enabled:
        return None
    hill_round = Round.objects.open_in(hill)
    if hill_round is None:
        return None
    return {
        'hill_round': hill_round,
        'attackers': hill_round.attempts.counted().values('identity').order_by().distinct().count(),
        'open': timezone.now() < hill_round.ends_at,
    }
