from django import forms
from django.contrib.auth.decorators import login_required
from django.contrib.sites.shortcuts import get_current_site
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.views.decorators.http import require_POST
from django.views.generic.base import ContextMixin
from django.views.generic.detail import DetailView
from django.views.generic.edit import FormView
from django.views.generic.list import ListView

from .forms import ChallengeWarriorForm
from .models import (
    Arena, Battle, BattleViewpoint, WarriorArena, WarriorUserPermission,
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

        battles_qs = Battle.objects.with_warrior_arena(
            self.object,
        )[:100].select_related(
            'text_unit_1_2',
            'text_unit_2_1',
        )
        battles = list(battles_qs)
        prefetch_warriors(battles)
        prefetch_warrior_arenas(self.object.arena, battles)
        context['battles'] = [
            battle.get_warrior_viewpoint(self.object)
            for battle in battles
        ]

        show_secrets = is_request_authorized(self.object.warrior, self.request)
        context['show_secrets'] = show_secrets
        context['warrior_user_permissions'] = None
        if self.request.user.is_authenticated:
            context['warrior_user_permission'] = WarriorUserPermission.objects.filter(
                warrior=self.object.warrior,
                user=self.request.user,
            ).first()

        # save the authorization for user if it's not already saved
        user = self.request.user
        if show_secrets and not self.object.warrior.is_user_authorized(user) and user.is_authenticated:
            WarriorUserPermission.objects.get_or_create(
                warrior=self.object.warrior,
                user=user,
            )

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
    warrior_arenas = {
        warrior_arena.warrior_id: warrior_arena
        for warrior_arena in WarriorArena.objects.filter(
            warrior_id__in=warrior_ids,
            arena=arena,
        )
    }
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
        self.battle = Battle.create_from_warriors(self.warrior, form.cleaned_data['warrior'])
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

        battle = self.object.battle
        battle.warrior_arena_1 = WarriorArena.objects.get(
            warrior=battle.warrior_1,
            arena=battle.arena,
        )
        battle.warrior_arena_2 = WarriorArena.objects.get(
            warrior=battle.warrior_2,
            arena=battle.arena,
        )

        # find prev/next battles
        battles_qs = Battle.objects.for_user(self.request.user).filter(
            arena_id=self.object.arena_id,
        )
        context['next_battle'] = battles_qs.filter(
            scheduled_at__gt=self.object.scheduled_at,
        ).order_by('scheduled_at').only('id', 'scheduled_at').first()
        context['previous_battle'] = battles_qs.filter(
            scheduled_at__lt=self.object.scheduled_at,
        ).order_by('-scheduled_at').only('id', 'scheduled_at').first()

        context['arena'] = self.object.arena

        return context


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
        qs = Battle.objects.filter(
            arena=self.arena,
        )
        if self.request.user.is_authenticated:
            qs = qs.for_user(self.request.user)
        else:
            authorized_warriors = self.request.session.get('authorized_warriors', [])
            qs = qs.filter(Q(
                warrior_1__id__in=authorized_warriors,
            ) | Q(
                warrior_2__id__in=authorized_warriors,
            )).distinct()
        qs = qs.order_by('-scheduled_at')
        battles = list(qs[:100])
        prefetch_warriors(battles)
        prefetch_warrior_arenas(self.arena, battles)
        return battles
