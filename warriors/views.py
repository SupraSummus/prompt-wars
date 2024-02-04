from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView

from .forms import WarriorCreateForm
from .models import Warrior


class WarriorCreateView(CreateView):
    model = Warrior
    form_class = WarriorCreateForm
    template_name = 'warriors/warrior_create.html'


class WarriorDetailView(DetailView):
    model = Warrior
