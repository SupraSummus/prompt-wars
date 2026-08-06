import uuid
from typing import NamedTuple

from django import forms
from django.contrib.auth.decorators import login_required
from django.contrib.sites.shortcuts import get_current_site
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.http import require_POST
from django.views.generic.base import ContextMixin
from django.views.generic.detail import DetailView
from django.views.generic.edit import FormView
from django.views.generic.list import ListView

from .battles import Battle, BattleViewpoint
from .forms import ChallengeWarriorForm
from .models import (
    Arena, WarriorArena, WarriorUserPermission, get_or_create_warrior_arenas,
)
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        warrior_arena = self.object
        battles_qs = Battle.objects.with_warrior_arena(
            warrior_arena,
        )[:100].prefetch_related(
            'game_scores',
        )
        battles = list(battles_qs)
        prefetch_warriors(battles)
        prefetch_warrior_arenas(warrior_arena.arena, battles)
        context['battles'] = [
            battle.get_warrior_viewpoint(warrior_arena, score_algorithm=warrior_arena.arena.score_algorithm)
            for battle in battles
        ]

        show_secrets = is_request_authorized(warrior_arena.warrior, self.request)
        context['show_secrets'] = show_secrets
        context['warrior_user_permissions'] = None
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
        self.battle, _, _ = Battle.create_from_warriors(self.warrior, form.cleaned_data['warrior'])
        return super().form_valid(form)

    def get_success_url(self):
        return self.battle.get_absolute_url()


def is_request_authorized(warrior, request):
    return (
        warrior.is_user_authorized(request.user) or
        str(warrior.id) in request.session.get('authorized_warriors', [])
    )


class BattleDetailView(DetailView):
    model = Battle
    context_object_name = 'battle'

    def get_object(self):
        battle = super().get_object()
        return BattleViewpoint(battle, '1')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        show_secrets_1 = is_request_authorized(self.object.warrior_1, self.request)
        show_secrets_2 = is_request_authorized(self.object.warrior_2, self.request)
        show_battle_results = (
            show_secrets_1 or show_secrets_2 or  # noqa: W504
            self.object.public_battle_results
        )

        # Add meta title
        context['meta_title'] = (
            f"Prompt Wars Battle: {self.object.warrior_1} vs {self.object.warrior_2}"
        )

        # Add meta description
        context['meta_description'] = (
            f"AI battle between '{self.object.warrior_1}' and '{self.object.warrior_2}'. "
            "View the results of this AI prompt engineering duel."
        )

        self.object.game_1_2.show_secrets_1 = show_secrets_1
        self.object.game_1_2.show_secrets_2 = show_secrets_2
        self.object.game_1_2.show_battle_results = show_battle_results
        self.object.game_2_1.show_secrets_1 = show_secrets_2
        self.object.game_2_1.show_secrets_2 = show_secrets_1
        self.object.game_2_1.show_battle_results = show_battle_results

        warrior_arena = get_nav_warrior_arena(self.request, self.object)
        context['nav_warrior_arena'] = warrior_arena
        context.update(battle_nav_context(self.object, warrior_arena))

        return context


def get_nav_warrior_arena(request, battle):
    """
    The warrior named by the `warrior_arena` query parameter, if it fought here.

    The warrior page puts the parameter on every link into a battle,
    so that stepping onward from there stays in the list it showed.
    A value naming no warrior of this battle names no warrior at all.
    """
    try:
        warrior_arena_id = uuid.UUID(request.GET.get('warrior_arena', ''))
    except ValueError:
        return None
    warrior_arena = WarriorArena.objects.filter(
        id=warrior_arena_id,
    ).select_related('arena').first()
    if warrior_arena is None:
        return None
    if warrior_arena.warrior_id not in (battle.warrior_1_id, battle.warrior_2_id):
        return None
    return warrior_arena


def battle_nav_context(battle, warrior_arena):
    """
    Links for the two walks through neighbouring battles in time.

    The arena walk is always offered, being all a battle URL supplies on its own;
    the warrior walk joins it once a warrior is named,
    stepping through the list `WarriorDetailView` shows.
    Both carry the warrior onward,
    so an arena step landing on another of its battles keeps the warrior walk.

    Each link addresses `battle_nav`, which is where a step is resolved,
    so offering four of them costs four `reverse` calls and no query.
    """
    context = {
        'arena_previous_battle_url': battle_url('previous_arena_battle', battle, warrior_arena),
        'arena_next_battle_url': battle_url('next_arena_battle', battle, warrior_arena),
        'warrior_previous_battle_url': None,
        'warrior_next_battle_url': None,
    }
    if warrior_arena is not None:
        context['warrior_previous_battle_url'] = battle_url('previous_warrior_battle', battle, warrior_arena)
        context['warrior_next_battle_url'] = battle_url('next_warrior_battle', battle, warrior_arena)
    return context


class TimeDirection(NamedTuple):
    """
    One side of a battle in time: previous is earlier, next is later.

    `side` keeps the battles lying that way,
    and `nearest_first` orders them so the closest one comes first.
    """
    side: str
    nearest_first: str


PREVIOUS = TimeDirection('scheduled_at__lt', '-scheduled_at')
NEXT = TimeDirection('scheduled_at__gt', 'scheduled_at')


def previous_arena_battle(request, pk):
    return battle_nav(request, pk, PREVIOUS, warrior_walk=False)


def next_arena_battle(request, pk):
    return battle_nav(request, pk, NEXT, warrior_walk=False)


def previous_warrior_battle(request, pk):
    return battle_nav(request, pk, PREVIOUS, warrior_walk=True)


def next_warrior_battle(request, pk):
    return battle_nav(request, pk, NEXT, warrior_walk=True)


def battle_nav(request, pk, direction, warrior_walk):
    """
    Redirect to the neighbour one step of one walk lands on.

    The battle page links here rather than resolving four neighbours
    on every render, for steps most of its visitors never take.
    The price is a link offered before anything looked for its target:
    a walk out of battles ends in a 404 here, not in an absent link.

    The two walks are the ones `battle_nav_context` offers,
    and a warrior step is only a step while the warrior is still named —
    the parameter is what says which list is being walked.
    """
    battle = get_object_or_404(Battle, pk=pk)
    warrior_arena = get_nav_warrior_arena(request, battle)
    if warrior_walk:
        if warrior_arena is None:
            raise Http404('This walk needs a warrior that fought here')
        battles = Battle.objects.with_warrior_arena(warrior_arena)
    else:
        battles = Battle.objects.for_user(request.user).filter(arena__llm=battle.llm)
    neighbour = battles.only('id', 'scheduled_at').filter(
        **{direction.side: battle.scheduled_at},
    ).order_by(direction.nearest_first).first()
    if neighbour is None:
        raise Http404('The walk ends here')
    return redirect(battle_url('battle_detail', neighbour, warrior_arena))


def battle_url(url_name, battle, warrior_arena):
    """A battle link that keeps the warrior whose list it was reached from, if any."""
    url = reverse(url_name, args=(battle.id,))
    if warrior_arena is not None:
        url += '?' + urlencode({'warrior_arena': warrior_arena.id})
    return url


class WarriorLeaderboard(ArenaViewMixin, ListView):
    model = WarriorArena
    template_name = 'warriors/warrior_leaderboard.html'
    context_object_name = 'warriors'

    def get_queryset(self):
        return WarriorArena.objects.battleworthy().filter(
            arena=self.arena,
        ).select_related(
            'warrior',
        ).order_by('-rating')[:100].only(
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
        qs = WarriorArena.objects.battleworthy().filter(arena=self.arena).select_related(
            'warrior',
        )
        user = self.request.user
        if user.is_authenticated:
            qs = qs.filter(warrior__users=user)
        else:
            authorized_warriors = self.request.session.get('authorized_warriors', [])
            qs = qs.filter(
                Q(id__in=authorized_warriors) |
                Q(warrior__id__in=authorized_warriors)
            )
        return qs.order_by('next_battle_schedule')[:100]


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
        qs = Battle.objects.filter(
            llm=self.arena.llm,
        ).filter(q).distinct().order_by('-scheduled_at')
        battles = list(qs[:100])
        prefetch_warriors(battles)
        prefetch_warrior_arenas(self.arena, battles)
        return battles
