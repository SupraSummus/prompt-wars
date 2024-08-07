from django import forms
from django.contrib.auth.decorators import login_required
from django.contrib.sites.shortcuts import get_current_site
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.views.decorators.http import require_POST
from django.views.generic.base import ContextMixin
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, FormView
from django.views.generic.list import ListView

from .forms import ChallengeWarriorForm, WarriorCreateForm
from .models import Arena, Battle, Warrior, WarriorUserPermission


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


class WarriorCreateView(ArenaViewMixin, CreateView):
    model = Warrior
    form_class = WarriorCreateForm
    template_name = 'warriors/warrior_create.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['arena'] = self.arena
        kwargs['user'] = self.request.user
        kwargs['session'] = self.request.session
        kwargs['request'] = self.request
        return kwargs


class WarriorViewMixin(ContextMixin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.warrior = None

    def dispatch(self, request, *args, pk=None, **kwargs):
        self.warrior = get_object_or_404(Warrior, id=pk)
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

        battles_qs = Battle.objects.with_warrior(
            self.object,
        )[:100].select_related(
            'warrior_1',
            'warrior_2',
        )
        context['battles'] = [
            battle.get_warrior_viewpoint(self.object)
            for battle in battles_qs
        ]

        show_secrets = is_request_authorized(self.object, self.request)
        context['show_secrets'] = show_secrets
        context['warrior_user_permissions'] = None
        if self.request.user.is_authenticated:
            context['warrior_user_permission'] = WarriorUserPermission.objects.filter(
                warrior=self.object,
                user=self.request.user,
            ).first()

        # save the authorization for user if it's not already saved
        user = self.request.user
        if show_secrets and not self.object.is_user_authorized(user) and user.is_authenticated:
            WarriorUserPermission.objects.get_or_create(
                warrior=self.object,
                user=user,
            )

        return context


class PublicBattleResutsForm(forms.Form):
    public_battle_results = forms.BooleanField(
        required=False,
        label='Public battle results',
    )


@require_POST
@login_required
def warrior_set_public_battle_results(request, pk):
    warrior_user_perm = get_object_or_404(WarriorUserPermission, warrior_id=pk, user=request.user)
    form = PublicBattleResutsForm(request.POST)
    if form.is_valid():
        warrior_user_perm.public_battle_results = form.cleaned_data['public_battle_results']
        warrior_user_perm.save(update_fields=['public_battle_results'])
        warrior_user_perm.warrior.update_public_battle_results()
    return redirect(warrior_user_perm.warrior.get_absolute_url())


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
        warrior.is_secret_valid(request.GET.get('secret', default='')) or  # noqa: W504
        warrior.is_user_authorized(request.user) or  # noqa: W504
        str(warrior.id) in request.session.get('authorized_warriors', [])
    )


class BattleDetailView(DetailView):
    model = Battle
    context_object_name = 'battle'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        show_secrets_1 = is_request_authorized(self.object.warrior_1, self.request)
        show_secrets_2 = is_request_authorized(self.object.warrior_2, self.request)
        show_battle_results = (
            show_secrets_1 or show_secrets_2 or  # noqa: W504
            self.object.public_battle_results
        )

        # Add meta title
        context['meta_title'] = f"Prompt Wars Battle: {self.object.warrior_1} vs {self.object.warrior_2}"

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
    model = Warrior
    template_name = 'warriors/warrior_leaderboard.html'
    context_object_name = 'warriors'

    def get_queryset(self):
        return Warrior.objects.battleworthy().filter(
            arena=self.arena,
        ).order_by('-rating')[:100]


class UpcomingBattlesView(ArenaViewMixin, ListView):
    model = Warrior
    template_name = 'warriors/upcoming_battles.html'
    context_object_name = 'warriors'

    def get_queryset(self):
        qs = Warrior.objects.battleworthy().exclude(
            next_battle_schedule=None,
        ).filter(arena=self.arena)
        user = self.request.user
        if user.is_authenticated:
            qs = qs.filter(users=user)
        else:
            qs = qs.filter(
                id__in=self.request.session.get('authorized_warriors', []),
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
        qs = qs.order_by('-scheduled_at').select_related(
            'warrior_1',
            'warrior_2',
        )
        return qs[:100]
