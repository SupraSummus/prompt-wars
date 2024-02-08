from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView
from django.views.generic.list import ListView

from .forms import WarriorCreateForm
from .models import Warrior


class WarriorCreateView(CreateView):
    model = Warrior
    form_class = WarriorCreateForm
    template_name = 'warriors/warrior_create.html'


class WarriorDetailView(DetailView):
    model = Warrior


class WarriorLeaderboard(ListView):
    model = Warrior
    template_name = 'warriors/warrior_leaderboard.html'
    context_object_name = 'warriors'

    def get_queryset(self):
        return Warrior.objects.battleworthy().order_by('-rating')[:100]
