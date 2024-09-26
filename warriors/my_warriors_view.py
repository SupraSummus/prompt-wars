from django.contrib.auth.decorators import login_required
from django.template.response import TemplateResponse

from djsfc import Router, parse_template

from .warriors import Warrior


router = Router(__name__)


template = parse_template('''\
{% extends "base.html" %}

{% block main %}
    <h1>My Warriors</h1>
    {% for warrior in warriors %}
        <div>
            <h2>{{ warrior.name }}</h2>
            <p>Rating: {{ warrior.rating }}</p>
            <p>Games played: {{ warrior.games_played }}</p>
        </div>
    {% endfor %}
{% endblock %}
''', router=router)


@router.route('GET', '')
@login_required
def index(request):
    warriors = Warrior.objects.filter(
        users=request.user,
    )
    context = {'warriors': warriors}
    return TemplateResponse(request, template, context)
