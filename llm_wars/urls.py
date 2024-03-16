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
from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path
from django.views.generic import TemplateView

import warriors.views
from users.views import SignupView
from warriors.views import (
    ArenaDetailView, BattleDetailView, ChallengeWarriorView, WarriorCreateView,
    WarriorDetailView, WarriorLeaderboard,
)


urlpatterns = [
    path('', TemplateView.as_view(template_name="home.html"), name='home'),
    path("admin/", admin.site.urls),

    path('create/', WarriorCreateView.as_view(), name='warrior_create'),
    path('warrior/<uuid:pk>', WarriorDetailView.as_view(), name='warrior_detail'),
    path('challenge/<uuid:pk>', ChallengeWarriorView.as_view(), name='challenge_warrior'),
    path('battle/<uuid:pk>', BattleDetailView.as_view(), name='battle_detail'),
    path('leaderboard/', WarriorLeaderboard.as_view(), name='warrior_leaderboard'),
    path('upcoming-battles/', warriors.views.UpcomingBattlesView.as_view(), name='upcoming_battles'),
    path('recent-battles/', warriors.views.RecentBattlesView.as_view(), name='recent_battles'),

    path('arenas/', warriors.views.arena_list, name='arena_list'),
    path('arena/<uuid:arena_id>/', ArenaDetailView.as_view(), name='arena_detail'),
    path('arena/<uuid:arena_id>/create/', WarriorCreateView.as_view(), name='arena_warrior_create'),
    path('arena/<uuid:arena_id>/leaderboard/', WarriorLeaderboard.as_view(), name='arena_leaderboard'),
    path('arena/<uuid:arena_id>/upcoming-battles/', warriors.views.UpcomingBattlesView.as_view(), name='arena_upcoming_battles'),
    path('arena/<uuid:arena_id>/recent-battles/', warriors.views.RecentBattlesView.as_view(), name='arena_recent_battles'),

    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('signup/', SignupView.as_view(), name='signup'),
]
