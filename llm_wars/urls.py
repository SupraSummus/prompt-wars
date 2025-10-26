"""
URL configuration for llm_wars project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path, register_converter
from django.views.generic import TemplateView

import warriors.views
from djsfc import Router
from users.views import SignupView
from warriors import my_warriors_view, warrior_view
from warriors.create_view import WarriorCreateView
from warriors.views import (
    ArenaDetailView, BattleDetailView, ChallengeWarriorView, WarriorDetailView,
    WarriorLeaderboard, warrior_set_public_battle_results,
)

from . import data_policy_view


class SignedIntConverter:
    regex = r'-?\d+'

    def to_python(self, value):
        return int(value)

    def to_url(self, value):
        return str(value)


register_converter(SignedIntConverter, 'signed_int')


router = Router(__name__)
router.route_all('my-warriors/', my_warriors_view.router, name='my_warriors')
router.route_all('warrior/', warrior_view.router, name='warrior')
router.route_all('data-policy/', data_policy_view.router, name='data_policy')

urlpatterns = (
    path('', TemplateView.as_view(template_name="home.html"), name='home'),
    path("admin/", admin.site.urls),

    # urls for default arena
    path('create/', WarriorCreateView.as_view(), name='warrior_create'),
    path('leaderboard/', WarriorLeaderboard.as_view(), name='warrior_leaderboard'),
    path('upcoming-battles/', warriors.views.UpcomingBattlesView.as_view(), name='upcoming_battles'),
    path('recent-battles/', warriors.views.RecentBattlesView.as_view(), name='recent_battles'),

    path('arenas/', warriors.views.arena_list, name='arena_list'),
    path('arena/<uuid:arena_id>/', ArenaDetailView.as_view(), name='arena_detail'),
    path('arena/<uuid:arena_id>/create/', WarriorCreateView.as_view(), name='arena_warrior_create'),
    path('arena/<uuid:arena_id>/leaderboard/', WarriorLeaderboard.as_view(), name='arena_leaderboard'),
    path('arena/<uuid:arena_id>/upcoming-battles/', warriors.views.UpcomingBattlesView.as_view(), name='arena_upcoming_battles'),
    path('arena/<uuid:arena_id>/recent-battles/', warriors.views.RecentBattlesView.as_view(), name='arena_recent_battles'),

    path('warrior-arena/<uuid:pk>/', WarriorDetailView.as_view(), name='warrior_detail'),
    path(
        'warrior/<uuid:pk>/set-public-battles/',
        warrior_set_public_battle_results,
        name='warrior_set_public_battles',
    ),
    path('challenge/<uuid:pk>/', ChallengeWarriorView.as_view(), name='challenge_warrior'),
    path('battle/<uuid:pk>/', BattleDetailView.as_view(), name='battle_detail'),

    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('signup/', SignupView.as_view(), name='signup'),
) + router.urls


if settings.ENABLE_DEBUG_TOOLBAR:
    from debug_toolbar.toolbar import debug_toolbar_urls
    urlpatterns += tuple(debug_toolbar_urls())
