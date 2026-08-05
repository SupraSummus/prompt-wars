import uuid

from django import forms
from django.contrib.auth.decorators import login_required
from django.contrib.sites.shortcuts import get_current_site
from django.db.models import Q
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

        warrior_arena = self.get_nav_warrior_arena()
        context['nav_warrior_arena'] = warrior_arena
        context['previous_battle_url'], context['next_battle_url'] = battle_nav_urls(
            self.object, warrior_arena, self.request.user,
        )

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


def battle_nav_urls(battle, warrior_arena, user):
    """
    Links to the battles either side of this one in time, older first.

    Given a warrior, they walk that warrior's battles —
    the list `WarriorDetailView` shows, so the two pages agree on
    what comes next — and carry the warrior onward.
    Without one they walk the arena, and the battle URL stands alone.
    """
    if warrior_arena is None:
        battles = Battle.objects.for_user(user).filter(arena__llm=battle.llm)
    else:
        battles = Battle.objects.with_warrior_arena(warrior_arena)
    battles = battles.only('id', 'scheduled_at')
    older = battles.filter(scheduled_at__lt=battle.scheduled_at).order_by('-scheduled_at').first()
    newer = battles.filter(scheduled_at__gt=battle.scheduled_at).order_by('scheduled_at').first()
    return battle_nav_url(older, warrior_arena), battle_nav_url(newer, warrior_arena)


def battle_nav_url(neighbour, warrior_arena):
    if neighbour is None:
        return None
    url = reverse('battle_detail', args=(neighbour.id,))
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
