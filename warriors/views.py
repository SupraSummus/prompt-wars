import datetime
import uuid

from django import forms
from django.contrib.auth.decorators import login_required
from django.contrib.sites.shortcuts import get_current_site
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from django.views.decorators.http import require_POST
from django.views.generic.base import ContextMixin
from django.views.generic.detail import DetailView
from django.views.generic.edit import FormView
from django.views.generic.list import ListView

from .battles import Battle
from .forms import ChallengeWarriorForm
from .models import (
    Arena, WarriorArena, WarriorUserPermission, get_or_create_warrior_arenas,
)
from .score import ScoreAlgorithm
from .stats import ArenaStats
from .warriors import Warrior


def arena_list(request):
    return TemplateResponse(request, 'warriors/arena_list.html', {
        'arenas': Arena.objects.filter(listed=True),
    })


class ArenaViewMixin(ContextMixin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.arena = None

    def dispatch(self, request, *args, arena_id=None, **kwargs):
        if arena_id is None:
            site = get_current_site(request)
            self.arena = get_object_or_404(Arena, site=site)
        else:
            self.arena = get_object_or_404(Arena, id=arena_id)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['arena'] = self.arena
        return context


class ArenaDetailView(ArenaViewMixin, DetailView):
    context_object_name = 'arena'
    template_name = 'warriors/arena_detail.html'

    def get_object(self):
        return self.arena

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['stats'] = ArenaStats.objects.filter(arena=self.arena).order_by('-date').first()

        return context


class WarriorViewMixin(ContextMixin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.warrior = None

    def dispatch(self, request, *args, pk=None, **kwargs):
        self.warrior = get_object_or_404(WarriorArena, id=pk)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['arena'] = self.warrior.arena
        context['warrior'] = self.warrior
        return context


class WarriorDetailView(WarriorViewMixin, DetailView):
    context_object_name = 'warrior'

    def get_object(self):
        return self.warrior

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        # A poll finding the page as it was swaps nothing,
        # so a keyboard or screen reader user keeps their place between real changes.
        polling = response.context_data['polling']
        if polling and request.GET.get('polling') == polling:
            return HttpResponse(status=204)
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        warrior_arena = self.object
        battles_qs = Battle.objects.with_warrior_arena(
            warrior_arena,
        )[:100].prefetch_related(
            # a battle score is the mean over its games,
            # and a game's score rows hang off the game they name
            'games__scores',
        )
        battles = list(battles_qs)
        prefetch_warriors(battles)
        prefetch_warrior_arenas(warrior_arena.arena, battles)
        context['battles'] = [
            warrior_battle_row(battle, warrior_arena)
            for battle in battles
        ]
        context['polling'] = warrior_page_polling(warrior_arena, context['battles'])
        context['poll_seconds'] = WARRIOR_POLL_SECONDS

        show_secrets = is_request_authorized(warrior_arena.warrior, self.request)
        context['show_secrets'] = show_secrets
        context['warrior_user_permission'] = None
        if self.request.user.is_authenticated:
            context['warrior_user_permission'] = WarriorUserPermission.objects.filter(
                warrior=warrior_arena.warrior,
                user=self.request.user,
            ).first()

        # save the authorization for user if it's not already saved
        user = self.request.user
        if show_secrets and not warrior_arena.warrior.is_user_authorized(user) and user.is_authenticated:
            WarriorUserPermission.objects.get_or_create(
                warrior=warrior_arena.warrior,
                user=user,
            )

        context['other_warrior_arenas'] = list(WarriorArena.objects.filter(
            warrior=warrior_arena.warrior,
            arena__listed=True,
        ).exclude(
            id=warrior_arena.id,
        ).select_related('arena'))

        return context


# A new spell's page refreshes itself while its author waits for the verdict and the first result;
# past this age nobody is watching it come in.
WARRIOR_POLL_WINDOW = datetime.timedelta(hours=1)
WARRIOR_POLL_SECONDS = 5


def warrior_page_polling(warrior_arena, battle_rows):
    """
    What part of a warrior's page polls for news, if any:
    the whole page while moderation decides what it shows,
    then the battle list until a first battle is scored.
    Only a fresh warrior's, as the first minutes are when a result is awaited
    (`get_next_battle_delay` front-loads its battles).
    """
    if timezone.now() - warrior_arena.created_at > WARRIOR_POLL_WINDOW:
        return None
    if warrior_arena.moderation_passed is None:
        return 'page'
    if warrior_arena.moderation_passed and all(row['performance'] == 'pending' for row in battle_rows):
        return 'battles'
    return None


def prefetch_warriors(battles):
    warrior_ids = {battle.warrior_1_id for battle in battles} | {battle.warrior_2_id for battle in battles}
    warriors = {
        warrior.id: warrior
        for warrior in Warrior.objects.filter(id__in=warrior_ids)
    }
    for battle in battles:
        battle.warrior_1 = warriors[battle.warrior_1_id]
        battle.warrior_2 = warriors[battle.warrior_2_id]


def prefetch_warrior_arenas(arena, battles):
    warrior_ids = {battle.warrior_1_id for battle in battles} | {battle.warrior_2_id for battle in battles}
    warrior_arenas = get_or_create_warrior_arenas(arena, warrior_ids)
    for battle in battles:
        battle.warrior_arena_1 = warrior_arenas[battle.warrior_1_id]
        battle.warrior_arena_2 = warrior_arenas[battle.warrior_2_id]


def warrior_battle_row(battle, warrior_arena):
    """
    One battle as the warrior's own list shows it: a score column per game.

    The games come this warrior-first,
    prompt order being the asymmetry the list is scanned for,
    and every number is that warrior's own
    ("The battle lists keep a score column per game"
    in docs/battle-display.md).
    The arena names the algorithm, being the one reader that has one.
    """
    warrior_id = warrior_arena.warrior_id
    algorithm = warrior_arena.arena.score_algorithm
    if battle.warrior_1_id == warrior_id:
        opponent, opponent_arena = battle.warrior_2, battle.warrior_arena_2
    else:
        opponent, opponent_arena = battle.warrior_1, battle.warrior_arena_1
    games = sorted(
        battle.games_list,
        key=lambda game: game.warrior_1_id != warrior_id,
    )
    if any(game.resolved_at is None for game in games):
        performance = 'pending'
    else:
        performance = format_performance(battle.warrior_performance(
            warrior_arena, opponent_arena, algorithm,
        ))
    return {
        'battle': battle,
        'url': battle_url(battle, warrior_arena),
        'opponent': opponent,
        'games': [
            {
                'game': game,
                'score': score_for(game.score_object(algorithm), warrior_id),
            }
            for game in games
        ],
        'performance': performance,
    }


def score_for(score_object, warrior_id):
    """One warrior's score, or nothing where the game is not scored yet."""
    return None if score_object is None else score_object.score_for(warrior_id)


def format_performance(performance):
    return 'none' if performance is None else f'{performance:+.2f}'


class PublicBattleResutsForm(forms.Form):
    public_battle_results = forms.BooleanField(
        required=False,
        label='Public battle results',
    )


@require_POST
@login_required
def warrior_set_public_battle_results(request, pk):
    warrior_user_perm = get_object_or_404(
        WarriorUserPermission,
        warrior__warrior_arenas__id=pk,
        user=request.user,
    )
    form = PublicBattleResutsForm(request.POST)
    warrior = warrior_user_perm.warrior
    if form.is_valid():
        warrior_user_perm.public_battle_results = form.cleaned_data['public_battle_results']
        warrior_user_perm.save(update_fields=['public_battle_results'])
        warrior.update_public_battle_results()
    return redirect('warrior_detail', pk)


class ChallengeWarriorView(WarriorViewMixin, FormView):
    form_class = ChallengeWarriorForm
    template_name = 'warriors/challenge_warrior.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['opponent'] = self.warrior
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['opponent'] = self.warrior
        return context

    def form_valid(self, form):
        self.battle = Battle.create_from_warriors(self.warrior, form.cleaned_data['warrior'])
        return super().form_valid(form)

    def get_success_url(self):
        return self.battle.get_absolute_url()


def is_request_authorized(warrior, request):
    return (
        warrior.is_user_authorized(request.user) or
        str(warrior.id) in request.session.get('authorized_warriors', [])
    )


def own_warrior_arenas(request):
    """
    The visitor's warriors on every arena: an account's,
    or what a logged-out browser created or discovered,
    whose session holds both warrior and warrior-arena ids (`WarriorCreateForm.save`).
    """
    if request.user.is_authenticated:
        return WarriorArena.objects.filter(warrior__users=request.user)
    ids = request.session.get('authorized_warriors', [])
    return WarriorArena.objects.filter(Q(id__in=ids) | Q(warrior__id__in=ids))


def claim_session_warriors(sender, request, user, **kwargs):
    """
    Give the user who just logged in the warriors this browser holds,
    which the session forgets on logout or expiry.
    It is the permission a logged-in visit to the warrior's page grants (`WarriorDetailView`).
    A `user_logged_in` receiver, so every way of logging in does it.
    """
    warrior_ids = Warrior.objects.filter(
        id__in=request.session.get('authorized_warriors', []),
    ).values_list('id', flat=True)
    WarriorUserPermission.objects.bulk_create(
        [WarriorUserPermission(warrior_id=warrior_id, user=user) for warrior_id in warrior_ids],
        ignore_conflicts=True,
    )


class BattleDetailView(DetailView):
    model = Battle
    context_object_name = 'battle'

    def get_queryset(self):
        # An unrated battle is not found here, whoever asks:
        # King of the Hill shows its battles on its own pages, under its own rules,
        # and authoring one side here (a hill boss that also plays the ladder)
        # must not open the other side's sealed result.
        return super().get_queryset().rated().select_related(
            'arena',
            'warrior_1',
            'warrior_2',
        ).prefetch_related(
            'games__warrior_1',
            'games__warrior_2',
            'games__scores',
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        battle = self.object

        # a warrior body, and the result read against it, are its author's
        visible_warrior_ids = {
            warrior.id
            for warrior in (battle.warrior_1, battle.warrior_2)
            if is_request_authorized(warrior, self.request)
        }
        show_battle_results = bool(visible_warrior_ids) or battle.public_battle_results

        # Add meta title
        context['meta_title'] = (
            f"Prompt Wars Battle: {battle.warrior_1} vs {battle.warrior_2}"
        )

        # Add meta description
        context['meta_description'] = (
            f"AI battle between '{battle.warrior_1}' and '{battle.warrior_2}'. "
            "View the results of this AI prompt engineering duel."
        )

        context['score_summaries'] = [
            battle_score_summary(battle, algorithm)
            for algorithm in ScoreAlgorithm
        ]
        context['game_blocks'] = [
            game_block(game, battle, visible_warrior_ids, show_battle_results)
            for game in battle.games_list
        ]

        warrior_arena = self.get_nav_warrior_arena()
        context['nav_warrior_arena'] = warrior_arena
        context.update(battle_nav_context(self.object, warrior_arena, self.request.user))

        return context

    def get_nav_warrior_arena(self):
        """
        The warrior named by the `warrior_arena` query parameter, if it fought here.

        The warrior page puts the parameter on every link into a battle,
        so that stepping onward from there stays in the list it showed.
        A value naming no warrior of this battle names no warrior at all.
        """
        try:
            warrior_arena_id = uuid.UUID(self.request.GET.get('warrior_arena', ''))
        except ValueError:
            return None
        warrior_arena = WarriorArena.objects.filter(
            id=warrior_arena_id,
        ).select_related('arena').first()
        if warrior_arena is None:
            return None
        if warrior_arena.warrior_id not in (self.object.warrior_1_id, self.object.warrior_2_id):
            return None
        return warrior_arena


def battle_sides(battle):
    """
    Each warrior's side of the page, keyed by warrior id.

    The battle's canonical order assigns them,
    and every block of the page reads its warriors in that order,
    so a warrior keeps one side and one color throughout
    ("A warrior keeps its side and color" in docs/battle-display.md).
    """
    return {battle.warrior_1_id: 1, battle.warrior_2_id: 2}


def battle_score_summary(battle, algorithm):
    """
    One algorithm's scores as a matrix: a warrior per row, a game per column.

    Every column sums to 1, the battle-score margin included,
    which is what a reader checks a symmetric presentation by
    (docs/battle-display.md, "The shape").
    Warrior similarity is per battle and per algorithm,
    so it sits beside the matrix rather than in a cell.
    """
    games = battle.games_list
    score_objects = [game.score_object(algorithm) for game in games]
    sides = battle_sides(battle)
    return {
        'algorithm': ScoreAlgorithm(algorithm).label,
        'games': [
            {'game': game, 'side': sides[game.warrior_1_id]}
            for game in games
        ],
        'rows': [
            {
                'warrior': warrior,
                'side': sides[warrior.id],
                'scores': [
                    score_for(score_object, warrior.id)
                    for score_object in score_objects
                ],
                'battle_score': battle.warrior_score(warrior.id, algorithm),
            }
            for warrior in (battle.warrior_1, battle.warrior_2)
        ],
        'warriors_similarity': next(
            (
                score_object.warriors_similarity
                for score_object in score_objects
                if score_object is not None
            ),
            None,
        ),
    }


def game_block(game, battle, visible_warrior_ids, show_battle_results):
    """
    One game as its own block: what the LLM produced, and how it scored.

    A game shows the algorithms that have scored it, each reporting itself,
    so a further member of `ScoreAlgorithm`
    reaches the page without a template edit (docs/battle-display.md).
    Prompt order is this game's own, so it is listed here
    rather than imposed on the scores below it.
    """
    sides = battle_sides(battle)
    return {
        'game': game,
        'prompt_order': [
            {'warrior': warrior, 'side': sides[warrior.id]}
            for warrior in (game.warrior_1, game.warrior_2)
        ],
        'result_visible': show_battle_results,
        'scorings': [
            game_scoring(game, battle, score_object, visible_warrior_ids)
            for score_object in (
                game.score_object(algorithm)
                for algorithm in ScoreAlgorithm
            )
            if score_object is not None
        ],
    }


def game_scoring(game, battle, score_object, visible_warrior_ids):
    """
    One algorithm's reading of one game.

    Marking the surviving text is LCS's own extra —
    an embedding similarity has nothing to mark —
    so it hangs off this block rather than the game's.
    """
    marks_result = score_object.algorithm == ScoreAlgorithm.LCS
    sides = battle_sides(battle)
    warriors = [
        {
            'warrior': warrior,
            'side': sides[warrior.id],
            'similarity': score_object.similarity_for(warrior.id),
            'score': score_object.score_for(warrior.id),
            'marked_result': (
                game.result_marked_for(warrior)
                if marks_result and warrior.id in visible_warrior_ids
                else None
            ),
        }
        for warrior in (battle.warrior_1, battle.warrior_2)
    ]
    return {
        'algorithm': ScoreAlgorithm(score_object.algorithm).label,
        # an errored game keeps its score rows, with nothing in them
        'scored': score_object.score is not None,
        'marks_result': marks_result,
        'marks_hidden': marks_result and any(
            warrior['marked_result'] is None for warrior in warriors
        ),
        'warriors': warriors,
        'cooperation_score': score_object.cooperation_score,
    }


def battle_nav_context(battle, warrior_arena, user):
    """
    Links for the two walks through neighbouring battles in time.

    The arena walk is always offered, being all a battle URL supplies on its own;
    the warrior walk joins it once a warrior is named,
    stepping through the list `WarriorDetailView` shows.
    Both carry the warrior onward,
    so an arena step landing on another of its battles keeps the warrior walk.
    """
    arena_previous, arena_next = battle_neighbour_urls(
        Battle.objects.for_user(user).rated().filter(arena__llm=battle.llm),
        battle, warrior_arena,
    )
    if warrior_arena is None:
        warrior_previous, warrior_next = None, None
    else:
        warrior_previous, warrior_next = battle_neighbour_urls(
            Battle.objects.with_warrior_arena(warrior_arena),
            battle, warrior_arena,
        )
    return {
        'arena_previous_battle_url': arena_previous,
        'arena_next_battle_url': arena_next,
        'warrior_previous_battle_url': warrior_previous,
        'warrior_next_battle_url': warrior_next,
    }


def battle_neighbour_urls(battles, battle, warrior_arena):
    """Links to the battles either side of this one within `battles`, older first."""
    battles = battles.only('id', 'scheduled_at')
    older = battles.filter(scheduled_at__lt=battle.scheduled_at).order_by('-scheduled_at').first()
    newer = battles.filter(scheduled_at__gt=battle.scheduled_at).order_by('scheduled_at').first()
    return battle_url(older, warrior_arena), battle_url(newer, warrior_arena)


def battle_url(battle, warrior_arena):
    """A battle link that keeps the warrior whose list it was reached from, if any."""
    if battle is None:
        return None
    url = reverse('battle_detail', args=(battle.id,))
    if warrior_arena is not None:
        url += '?' + urlencode({'warrior_arena': warrior_arena.id})
    return url


class WarriorLeaderboard(ArenaViewMixin, ListView):
    model = WarriorArena
    template_name = 'warriors/warrior_leaderboard.html'
    context_object_name = 'warriors'

    def get_queryset(self):
        return WarriorArena.objects.ranked().filter(
            arena=self.arena,
        ).select_related(
            'warrior',
        )[:100].only(
            'rating',
            'rating_playstyle',
            'games_played',
            'warrior__name',
            'warrior__moderation_passed',
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        warriors = self.get_queryset()
        playstyle_data = [
            {
                'x': warrior.rating_playstyle[0],
                'y': warrior.rating_playstyle[1],
                'name': str(warrior)
            }
            for warrior in warriors
            if warrior.rating_playstyle
        ]
        context['playstyle_data'] = playstyle_data
        return context


class UpcomingBattlesView(ArenaViewMixin, ListView):
    model = WarriorArena
    template_name = 'warriors/upcoming_battles.html'
    context_object_name = 'warriors'

    def get_queryset(self):
        return own_warrior_arenas(self.request).battleworthy().filter(
            arena=self.arena,
        ).select_related(
            'warrior',
        ).order_by('next_battle_schedule')[:100]


class RecentBattlesView(ArenaViewMixin, ListView):
    model = Battle
    template_name = 'warriors/recent_battles.html'
    context_object_name = 'battles'

    def get_queryset(self):
        # Show battles where results are viewable:
        # - user owns one of the warriors, OR
        # - one of the warriors has public_battle_results=True, OR
        # - user has authorized access via session
        q = Q(warrior_1__public_battle_results=True) | Q(warrior_2__public_battle_results=True)
        if self.request.user.is_authenticated:
            q |= Q(warrior_1__users=self.request.user) | Q(warrior_2__users=self.request.user)
        authorized_warriors = self.request.session.get('authorized_warriors', [])
        if authorized_warriors:
            q |= Q(warrior_1__id__in=authorized_warriors) | Q(warrior_2__id__in=authorized_warriors)
        qs = Battle.objects.rated().filter(
            llm=self.arena.llm,
        ).filter(q).distinct().order_by('-scheduled_at')
        battles = list(qs[:100])
        prefetch_warriors(battles)
        prefetch_warrior_arenas(self.arena, battles)
        return battles
