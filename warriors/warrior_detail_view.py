from collections import Counter

from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse

from djsfc import Router, parse_template

from .models import Battle, WarriorArena, WarriorUserPermission
from .views import is_request_authorized


router = Router(__name__)


template = parse_template('''\
{% extends "base.html" %}

{% block title %}{{ warrior.name }} - Global Warrior Details{% endblock %}

{% block main %}
  <h1>{{ warrior.name }} (Global Warrior)</h1>

  <div class="grid">
    <div>
      <h2>Stats</h2>
      <ul>
        <li>Rating: {{ warrior.rating|floatformat:2 }}</li>
        <li>Win Rate: {{ warrior.win_rate|default:"N/A"|floatformat:2 }}%</li>
        <li>Total Battles: {{ total_battles }}</li>
        <li>Arena: {{ arena.name }}</li>
        <li>Created: {{ warrior.created_at|date:"F j, Y" }}</li>
        {% if last_battle %}
          <li>Last Battle: {{ last_battle.scheduled_at|date:"F j, Y" }}</li>
        {% endif %}
      </ul>

      {% if warrior.rating_playstyle %}
        <h3>Playstyle</h3>
        <ul>
          {% for style in warrior.rating_playstyle %}
            <li>{{ style|floatformat:2 }}</li>
          {% endfor %}
        </ul>
      {% endif %}
    </div>

    <div>
      {% if show_secrets %}
        <h2>Warrior Prompt</h2>
        <pre><code>{{ warrior.body }}</code></pre>
      {% endif %}

      {% if warrior_user_permission %}
        <h3>Settings</h3>
        <form method="post" action="{% url 'warrior_set_public_battles' warrior.id %}">
          {% csrf_token %}
          <label>
            <input type="checkbox" name="public_battle_results"
                   {% if warrior_user_permission.public_battle_results %}checked{% endif %}>
            Public battle results
          </label>
          <button type="submit">Save</button>
        </form>
      {% endif %}
    </div>
  </div>

  <h2>Top Opponents</h2>
  {% if top_opponents %}
    <ul>
      {% for opponent, count in top_opponents %}
        <li>
          <a href="{% url 'global_warrior_detail' opponent.id %}">{{ opponent.name }}</a> ({{ count }} battles)
        </li>
      {% endfor %}
    </ul>
  {% else %}
    <p>No battles yet.</p>
  {% endif %}

  <h2>Recent Battles</h2>
  {% if battles %}
    <ul>
      {% for battle in battles %}
        <li>
          <a href="{{ battle.get_absolute_url }}">
            vs {{ battle.opponent.name }} - {{ battle.result }}
          </a>
        </li>
      {% endfor %}
    </ul>
  {% else %}
    <p>No recent battles.</p>
  {% endif %}

  <a href="{% url 'challenge_warrior' warrior.id %}" role="button">Challenge this warrior</a>
{% endblock %}
''', router=router)


@router.route('GET', '<uuid:warrior_id>/')
def warrior_detail(request, warrior_id):
    warrior = get_object_or_404(WarriorArena, id=warrior_id)

    battles_qs = Battle.objects.with_warrior(warrior).select_related(
        'warrior_1', 'warrior_1__warrior', 'warrior_2', 'warrior_2__warrior'
    )

    show_secrets = is_request_authorized(warrior, request)
    warrior_user_permission = None
    if request.user.is_authenticated:
        warrior_user_permission = WarriorUserPermission.objects.filter(
            warrior=warrior.warrior,
            user=request.user,
        ).first()

    top_opponents = Counter(
        battle.opponent(warrior) for battle in battles_qs
    ).most_common(5)

    context = {
        'warrior': warrior,
        'total_battles': battles_qs.count(),
        'battles': [battle.get_warrior_viewpoint(warrior) for battle in battles_qs[:100]],
        'show_secrets': show_secrets,
        'warrior_user_permission': warrior_user_permission,
        'last_battle': battles_qs.order_by('-scheduled_at').first(),
        'top_opponents': top_opponents,
        'arena': warrior.arena,
    }

    return TemplateResponse(request, template, context)
