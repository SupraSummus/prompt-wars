from functools import cached_property

from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView
from django.views.generic.list import ListView

from .forms import WarriorCreateForm
from .models import Battle, Warrior, WarriorUserPermission


class WarriorCreateView(CreateView):
    model = Warrior
    form_class = WarriorCreateForm
    template_name = 'warriors/warrior_create.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_success_url(self):
        return self.object.get_absolute_url_secret()


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

        show_secrets = self.is_secret_valid or self.is_user_authorized
        user = self.request.user
        if show_secrets and not self.is_user_authorized and user.is_authenticated:
            WarriorUserPermission.objects.create(
                warrior=self.object,
                user=user,
            )
        context['show_secrets'] = show_secrets

        return context

    @cached_property
    def is_secret_valid(self):
        secret = self.request.GET.get('secret', default='')
        return self.object.is_secret_valid(secret)

    @cached_property
    def is_user_authorized(self):
        return self.object.is_user_authorized(self.request.user)


class BattleDetailView(DetailView):
    model = Battle
    context_object_name = 'battle'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        secret = self.request.GET.get('secret', default='')
        context['show_secrets_1'] = (
            self.object.warrior_1.is_secret_valid(secret) or  # noqa: W504
            self.object.warrior_1.is_user_authorized(self.request.user)
        )
        context['show_secrets_2'] = (
            self.object.warrior_2.is_secret_valid(secret) or  # noqa: W504
            self.object.warrior_2.is_user_authorized(self.request.user)
        )
        context['show_secrets'] = context['show_secrets_1'] or context['show_secrets_2']

        return context


class WarriorLeaderboard(ListView):
    model = Warrior
    template_name = 'warriors/warrior_leaderboard.html'
    context_object_name = 'warriors'

    def get_queryset(self):
        return Warrior.objects.battleworthy().order_by('-rating')[:100]
