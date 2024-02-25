from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView
from django.views.generic.list import ListView

from .forms import WarriorCreateForm
from .models import Arena, Battle, Warrior, WarriorUserPermission


class ArenaViewMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.arena = None

    def dispatch(self, request, *args, arena_id=None, **kwargs):
        if arena_id is None:
            arena_id = settings.DEFAULT_ARENA_ID
        self.arena = get_object_or_404(Arena, id=arena_id)
        return super().dispatch(request, *args, **kwargs)


class WarriorCreateView(ArenaViewMixin, CreateView):
    model = Warrior
    form_class = WarriorCreateForm
    template_name = 'warriors/warrior_create.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['arena'] = self.arena
        kwargs['user'] = self.request.user
        kwargs['session'] = self.request.session
        return kwargs


class WarriorDetailView(DetailView):
    model = Warrior
    context_object_name = 'warrior'

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

        # save the authorization for user if it's not already saved
        user = self.request.user
        if show_secrets and not self.object.is_user_authorized(user) and user.is_authenticated:
            WarriorUserPermission.objects.get_or_create(
                warrior=self.object,
                user=user,
            )

        return context


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
        self.object.game_1_2.show_secrets_1 = show_secrets_1
        self.object.game_1_2.show_secrets_2 = show_secrets_2
        self.object.game_2_1.show_secrets_1 = show_secrets_2
        self.object.game_2_1.show_secrets_2 = show_secrets_1

        battles_qs = Battle.objects.for_user(self.request.user)
        context['next_battle'] = battles_qs.filter(
            scheduled_at__gt=self.object.scheduled_at,
        ).order_by('scheduled_at').only('id', 'scheduled_at').first()
        context['previous_battle'] = battles_qs.filter(
            scheduled_at__lt=self.object.scheduled_at,
        ).order_by('-scheduled_at').only('id', 'scheduled_at').first()

        return context


class WarriorLeaderboard(ArenaViewMixin, ListView):
    model = Warrior
    template_name = 'warriors/warrior_leaderboard.html'
    context_object_name = 'warriors'

    def get_queryset(self):
        return Warrior.objects.battleworthy().filter(
            arena=self.arena,
        ).order_by('-rating')[:100]


class UpcomingBattlesView(ListView):
    model = Warrior
    template_name = 'warriors/upcoming_battles.html'
    context_object_name = 'warriors'

    def get_queryset(self):
        qs = Warrior.objects.battleworthy().exclude(
            next_battle_schedule=None,
        )
        user = self.request.user
        if user.is_authenticated:
            qs = qs.filter(users=user)
        else:
            qs = qs.filter(
                id__in=self.request.session.get('authorized_warriors', []),
            )
        return qs.order_by('next_battle_schedule')[:100]


class RecentBattlesView(ListView):
    model = Battle
    template_name = 'warriors/recent_battles.html'
    context_object_name = 'battles'

    def get_queryset(self):
        qs = Battle.objects.all()
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
