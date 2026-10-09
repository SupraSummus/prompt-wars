"""
King of the Hill's pages: the hill, an attack, an attempt and its status poll, and a past round.

Thin over the backend:
`hill.attack.submit_attack` takes an attack, `hill.status` says where an attempt stands,
`hill.rules` who may see it, and `hill.display` what a page shows of it.
A GET reads the player's identity without creating one (`peek_identity`),
so a visitor who only looks leaves no session behind.
"""
import uuid

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone

from djsfc import Router

from . import status
from .attack import (
    VERIFIED_ROUND_SESSION_KEY, Accepted, Refused, captcha_needed,
    entry_refusal, submit_attack,
)
from .display import (
    attempt_meta, battle_view, index_meta, reign_line, round_meta, share_text,
    shown_state, standing_of, standing_rows,
)
from .forms import HillAttackForm
from .identity import peek_identity
from .models import AttemptState, BossReason, Hill, HillAttempt, Round
from .rules import (
    HILL_ATTEMPTS_PER_PLAYER, HILL_MIN_SURVIVED_CHARS, HILL_WIN_SCORE,
    beats_boss, crowned_round, is_public, replies_public, standings,
    standings_stats,
)


router = Router(__name__)

# How often an attempt's page asks whether its status changed:
# a result shows within seconds of arriving, and an unchanged answer is an empty 204.
HILL_POLL_SECONDS = 3

# the rules the pages quote
RULES = {
    'win_score': HILL_WIN_SCORE,
    'attempts_per_player': HILL_ATTEMPTS_PER_PLAYER,
    'min_survived_chars': HILL_MIN_SURVIVED_CHARS,
}

# what a terminal status poll returns once the hill is switched off: no `hx-*`, so polling stops
CLOSED_STATUS = '<section id="attempt-status"><p role="status">King of the Hill is closed.</p></section>'


def _page_context(request, **context):
    """Context every hill page has: its address without the query, for link previews."""
    return {
        'canonical_url': request.build_absolute_uri(request.path),
        'noindex': False,
        **context,
    }


def _closed(request, hill, hill_round, kept_body=''):
    """
    The page for a hill that is off, or on but not yet seeded; None when it is open.

    `kept_body` is an attack's text that arrived while it was off, handed back to copy.
    """
    if hill is not None and hill.enabled and hill_round is not None:
        return None
    return TemplateResponse(request, 'hill/closed.html', _page_context(
        request,
        opens_soon=hill is not None and hill.enabled,
        kept_body=kept_body,
        meta_title='King of the Hill',
        meta_description='Attack the boss spell of the day on Prompt Wars.',
    ))


def _attempts_with_status_data():
    return status.with_status_data(HillAttempt.objects.select_related(
        'hill_round__boss',
    ).defer(
        'hill_round__boss__voyage_3_embedding',
    ))


def _public_battle(attempt_id, crowned):
    """
    The battle by which an attempt took the hill, for anyone to see; None if it can't be shown.

    `crowned` is a round the attempt's spell held the hill in, which names it.
    """
    attempt = _attempts_with_status_data().filter(id=attempt_id).first()
    if attempt is None or attempt.state != AttemptState.SCORED or not is_public(attempt):
        return None
    return battle_view(
        attempt,
        attacker_label=crowned.boss_label,
        boss_label=attempt.hill_round.boss_label,
        replies=replies_public(attempt),
    )


def _initial(request):
    """
    The attack form's starting values: with `?from=`, the player's earlier attack.

    `?from=` is honoured only for the attempt's own author,
    so a shared attempt link can't open a sealed spell in a stranger's form.
    """
    try:
        earlier_id = uuid.UUID(request.GET.get('from', ''))
    except ValueError:
        return {}
    earlier = HillAttempt.objects.filter(id=earlier_id).select_related('warrior').first()
    if earlier is None or earlier.identity != peek_identity(request):
        return {}
    return {
        'body': earlier.warrior.body,
        'display_name': earlier.display_name,
        'display_author': earlier.display_author,
    }


def _attacks_left(hill_round, identity):
    return max(0, HILL_ATTEMPTS_PER_PLAYER - hill_round.attempts.live().filter(identity=identity).count())


def _hill_page(request, hill, hill_round, form, refusal=None):
    """
    The hill: the boss, the attack form, the standings and the round before.

    Opened afresh, the form gives way to whatever keeps the visitor from attacking now;
    after a refused attack it stays, holding the visitor's text, under the reason.
    """
    now = timezone.now()
    identity = peek_identity(request)
    entry = None if form.is_bound else entry_refusal(hill, hill_round, identity, now)
    busy = entry is not None and entry.code == 'busy'
    blocked = None if busy else entry
    rows = standings(hill_round)
    stats = standings_stats(rows)
    boss_attempt = hill_round.boss_attempt
    previous = Round.objects.filter(
        hill=hill,
        number=hill_round.number - 1,
        closed_at__isnull=False,
    ).first()
    your_attempts = [] if identity is None else hill_round.attempts.filter(
        identity=identity,
    ).select_related(
        'warrior',
    ).defer(
        'warrior__voyage_3_embedding',
    )
    return TemplateResponse(request, 'hill/index.html', _page_context(
        request,
        hill=hill,
        hill_round=hill_round,
        round_open=now < hill_round.ends_at,
        reign_line=reign_line(hill_round),
        stats=stats,
        holder=boss_attempt is not None and boss_attempt.identity == identity,
        form=form,
        refusal=refusal,
        blocked=blocked,
        busy_count=HillAttempt.objects.filter(state=AttemptState.PENDING).count() if busy else 0,
        in_flight=(
            HillAttempt.objects.filter(identity=identity, state=AttemptState.PENDING).first()
            if blocked is not None and blocked.code == 'in_flight' else None
        ),
        attacks_left=_attacks_left(hill_round, identity) if identity is not None else None,
        captcha_needed=captcha_needed(request, hill_round, identity),
        crowning=_public_battle(boss_attempt.id, hill_round) if boss_attempt is not None else None,
        your_attempts=[{'attempt': mine, 'state': shown_state(mine, mine.state)} for mine in your_attempts],
        standings=standing_rows(rows, identity),
        previous=previous,
        previous_stats=standings_stats(standings(previous)) if previous is not None else None,
        **RULES,
        **index_meta(hill_round, stats),
    ))


@router.route('GET', '')
def index(request):
    hill = Hill.current()
    hill_round = Round.objects.open_in(hill)
    closed = _closed(request, hill, hill_round)
    if closed is not None:
        return closed
    return _hill_page(request, hill, hill_round, HillAttackForm(initial=_initial(request)))


@router.route('POST', 'attack/')
def attack(request):
    hill = Hill.current()
    hill_round = Round.objects.open_in(hill)
    closed = _closed(request, hill, hill_round, kept_body=request.POST.get('body', ''))
    if closed is not None:
        return closed
    form = HillAttackForm(request.POST, captcha=captcha_needed(request, hill_round, peek_identity(request)))
    valid = form.is_valid()
    if 'captcha' in form.cleaned_data:
        # solved: it counts for the round, whatever becomes of this attack
        request.session[VERIFIED_ROUND_SESSION_KEY] = str(hill_round.id)
    if not valid:
        return _hill_page(request, hill, hill_round, form)
    try:
        accepted = submit_attack(
            request,
            round_number=form.cleaned_data['round_number'],
            body=form.cleaned_data['body'],
            display_name=form.cleaned_data['display_name'],
            display_author=form.cleaned_data['display_author'],
        )
    except Refused as refused:
        return _refused(request, form, refused)
    if accepted.repeated:
        messages.info(request, Accepted.REPEAT_NOTICE)
    return redirect('hill:attempt', accepted.attempt.id)


def _refused(request, form, refused):
    """The hill again after a refused attack: the reason, over the visitor's text, aimed at the boss on the hill now."""
    hill = Hill.current()
    hill_round = Round.objects.open_in(hill)
    closed = _closed(request, hill, hill_round, kept_body=request.POST.get('body', ''))
    if closed is not None:
        return closed
    return _hill_page(request, hill, hill_round, form, refusal=refused)


def _settled_state(attempt):
    """Where the attempt stands now, as pages show it (`shown_state`), stored first if it has just reached an outcome."""
    state = status.attempt_status(attempt)
    if state != AttemptState.PENDING and attempt.state == AttemptState.PENDING:
        if not status.finalize_attempt(attempt, state):
            # stored meanwhile by the sweep or another poll, with the same values
            attempt.refresh_from_db(fields=['state', 'score', 'survived_chars', 'crown_block'])
            state = attempt.state
    return shown_state(attempt, state)


def _attempt_context(request, attempt):
    """
    What an attempt's page and its status poll show this viewer.

    Its author sees all of it; anyone else sees the score only,
    unless the attempt took the hill (`hill.rules.is_public`),
    and then the replies only once moderation passed them.
    """
    now = timezone.now()
    state = _settled_state(attempt)
    identity = peek_identity(request)
    own = attempt.identity == identity
    public = not own and is_public(attempt)
    hill_round = attempt.hill_round
    context = {
        **RULES,
        'hill_round': hill_round,
        'attempt': attempt,
        'state': state,
        'key': status.stage_key(attempt, state, now),
        'polling': state == AttemptState.PENDING,
        'poll_seconds': HILL_POLL_SECONDS,
        'own': own,
        'public': public,
        'battle': None,
        'beats_boss': state == AttemptState.SCORED and beats_boss(attempt),
        'standing': None,
        'standings_total': 0,
        'share_text': '',
        'attacks_left': None,
        'round_open': hill_round.closed_at is None and now < hill_round.ends_at,
    }
    if state == AttemptState.SCORED and (own or public):
        context['battle'] = battle_view(
            attempt,
            attacker_label='You' if own else crowned_round(attempt).boss_label,
            attacker_spell='your spell' if own else None,
            boss_label=hill_round.boss_label,
            replies=own or replies_public(attempt),
        )
    if own and state == AttemptState.SCORED:
        if not attempt.late:
            context['standing'], context['standings_total'] = standing_of(hill_round, identity)
        context['share_text'] = share_text(
            context['battle'],
            hill_round,
            request.build_absolute_uri(reverse('hill:index')),
            holding_round=Round.objects.filter(boss_attempt=attempt, closed_at=None).first(),
        )
    if own and context['round_open']:
        context['attacks_left'] = _attacks_left(hill_round, identity)
    return context


def _attempt_or_404(attempt_id):
    return get_object_or_404(_attempts_with_status_data(), id=attempt_id)


@router.route('GET', 'a/<uuid:attempt_id>/')
def attempt(request, attempt_id):
    hill = Hill.current()
    today = Round.objects.open_in(hill)
    closed = _closed(request, hill, today)
    if closed is not None:
        return closed
    shown = _attempt_or_404(attempt_id)
    context = _attempt_context(request, shown)
    # an old link: point at the round that is open now
    context['today'] = today if shown.hill_round.closed_at is not None else None
    return TemplateResponse(request, 'hill/attempt.html', _page_context(
        request,
        noindex=True,
        **context,
        **attempt_meta(shown, context['state']),
    ))


@router.route('GET', 'a/<uuid:attempt_id>/status/')
def attempt_status(request, attempt_id):
    """
    The htmx poll behind an attempt's page: 204 while nothing visible changed,
    else the status block again, without `hx-*` once the outcome is in, which ends the polling.
    """
    hill = Hill.current()
    if hill is None or not hill.enabled:
        return HttpResponse(CLOSED_STATUS)
    context = _attempt_context(request, _attempt_or_404(attempt_id))
    if context['polling'] and context['key'] == request.GET.get('key'):
        return HttpResponse(status=204)
    return TemplateResponse(request, 'hill/partials/attempt_status.html', context)


@router.route('GET', 'round/<int:number>/')
def round_detail(request, number):
    hill = Hill.current()
    today = Round.objects.open_in(hill)
    closed = _closed(request, hill, today)
    if closed is not None:
        return closed
    hill_round = get_object_or_404(
        Round.objects.select_related('boss').defer('boss__voyage_3_embedding'),
        hill=hill,
        number=number,
    )
    if hill_round.closed_at is None:
        return redirect('hill:index')
    following = Round.objects.filter(
        hill=hill,
        number=number + 1,
    ).select_related(
        'boss',
        'boss_attempt',
    ).defer(
        'boss__voyage_3_embedding',
    ).first()
    crowning = None
    if following is not None and following.boss_reason in (BossReason.BROKE, BossReason.INHERITED):
        crowning = _public_battle(following.boss_attempt_id, following)
    stats = standings_stats(standings(hill_round))
    return TemplateResponse(request, 'hill/round.html', _page_context(
        request,
        hill=hill,
        hill_round=hill_round,
        stats=stats,
        following=following,
        crowning=crowning,
        today=today,
        **round_meta(hill_round, stats),
    ))
