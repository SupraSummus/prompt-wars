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
from django.contrib.auth.views import LogoutView
from django.urls import path, register_converter

import warriors.views
from djsfc import Router
from embedding_explorer import views as embedding_explorer_views
from guessing import views as guessing_views
from hill import views as hill_views
from users import connect_password, google_login
from users.views import LoginView, SignupView
from warriors import my_warriors_view
from warriors.create_view import WarriorCreateView
from warriors.views import (
    ArenaPageRedirect, BattleDetailView, ChallengeWarriorView,
    WarriorDetailView, WarriorLeaderboard, legacy_warrior_arena,
    warrior_set_public_battle_results,
)

from . import data_policy_view, home_view


class SignedIntConverter:
    regex = r'-?\d+'

    def to_python(self, value):
        return int(value)

    def to_url(self, value):
        return str(value)


register_converter(SignedIntConverter, 'signed_int')


router = Router(__name__)
router.route_all('my-warriors/', my_warriors_view.router, name='my_warriors')
router.route_all('data-policy/', data_policy_view.router, name='data_policy')
router.route_all('embedding-explorer/', embedding_explorer_views.router, name='embedding_explorer')
router.route_all('guessing/', guessing_views.router, name='guessing')
router.route_all('hill/', hill_views.router, name='hill')
router.route_all('login/google/', google_login.router, name='google_login')
router.route_all('login/connect-password/', connect_password.router, name='connect_password')

urlpatterns = (
    path('', home_view.home, name='home'),
    path("admin/", admin.site.urls),

    path('create/', WarriorCreateView.as_view(), name='warrior_create'),
    path('leaderboard/', warriors.views.leaderboard_redirect, name='warrior_leaderboard'),
    path('leaderboard/<str:ranking>/', WarriorLeaderboard.as_view(), name='ranking_leaderboard'),
    path('upcoming-battles/', warriors.views.UpcomingBattlesView.as_view(), name='upcoming_battles'),
    path('recent-battles/', warriors.views.RecentBattlesView.as_view(), name='recent_battles'),

    # The arena pages, linked from outside, land on what replaced them.
    path('arenas/', ArenaPageRedirect.as_view(pattern_name='warrior_leaderboard')),
    *[
        path(f'arena/<uuid:arena_id>/{page}', ArenaPageRedirect.as_view(pattern_name=name))
        for page, name in (
            ('', 'home'),
            ('create/', 'warrior_create'),
            ('leaderboard/', 'warrior_leaderboard'),
            ('upcoming-battles/', 'upcoming_battles'),
            ('recent-battles/', 'recent_battles'),
        )
    ],

    path('warrior/<uuid:pk>/', WarriorDetailView.as_view(), name='warrior_detail'),
    path('warrior-arena/<uuid:pk>/', legacy_warrior_arena),
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
