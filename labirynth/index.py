from django.contrib.auth.decorators import login_required
from django.template.response import TemplateResponse

from djsfc import Router, get_template_block, parse_template

from .models import Player


router = Router(__name__)


template_str = """\
{% extends "base.html" %}

{% block content %}<main class="container"
  hx-target="this"
>

  {% if not current_room %}
    <h1>The labirynth</h1>
    <p>Labirynth spans all around. You are in the middle of intricate maze of rooms.</p>
    <p>Do you want to escape? Or maybe just chill here and explore?</p>
    <form hx-post="{% url ':start' %}" hx-swap="outerHTML">
      {% csrf_token %}
      <button type="submit">Enter the first room</button>
    </form>

  {% elif current_room.is_empty %}
    <h1>Wow! You escaped!</h1>
    <p>Maybe you want to extend the labirynth here?</p>
    <form hx-post="{% url ':add_room' %}" hx-swap="outerHTML">
      {% csrf_token %}
      {{ new_room_form.as_div }}
      <button type="submit">Add a new room</button>
    </form>
    <p>Or start over?</p>
    <form hx-post="{% url ':start' %}" hx-swap="outerHTML">
      {% csrf_token %}
      <button type="submit">Go to the first room</button>
    </form>

  {% else %}
    <h1>{{ current_room }}</h1>
    <ul>
      {% for direction in directions %}
        <li>
          {% if direction.is_locked %}
            {{ direction.name }} - door is locked
          {% else %}
            {{ direction.name }}
            <form hx-post="{% url ':move' %}" hx-swap="outerHTML">
              {% csrf_token %}
              {{ direction.form.as_div }}
              <button type="submit">Go {{ direction.name }}</button>
            </form>
          {% endif %}
        </li>
      {% endfor %}
    </ul>

    <p>You may cast a spell to open a door. Hopefully.</p>
    {% block spell_cast %}

      {% if current_visit.state == 'spelling' %}
        <form hx-post="{% url ':cast' %}" hx-swap="outerHTML" hx-target="this">
          {% csrf_token %}
          {{ spell_form.as_p }}
          <button type="submit">Cast a spell</button>
        </form>

      {% elif current_visit.state == 'error' %}
        <p>The room is confused. Every door unlocks.</p>

      {% else %}
        <p>Your spell echoes in the room.</p>
        {% if current_visit.state == 'echoing' %}
          <div aria-busy="true"></div>
        {% elif current_visit.state == 'embedding' %}
          <p>You hear...</p>
          {% include 'excat_text.html' with text=current_visit.echo %}

        {% elif current_visit.state == 'embedding' %}
          <p>It's getting embedded...</p>

        {% else %}
          <p>It's done! The door is open.</p>

        {% endif %}

      {% endif %}
    {% endblock %}

    <p>Desperate or deadlocked? You can always start over.</p>
    <form hx-post="{% url ':start' %}" hx-swap="outerHTML">
      {% csrf_token %}
      <button type="submit">Go to the first room</button>
    </form>

  {% endif %}

</main>{% endblock %}
"""
template = parse_template(template_str, router)
content_block_template = get_template_block(template, 'content')


@router.route('GET', '')
@login_required
def root(request):
    room = get_room(request)
    context = {
        'current_room': room,
    }
    if room:
        context['room_prompt'] = room.prompt
    return TemplateResponse(request, template, context)


@router.route('POST', 'start')
def start(request):
    player, created = Player.objects.get_or_create(user=request.user)
    return TemplateResponse(request, content_block_template, {
        'current_room': player.current_room,
    })


def get_room(request):
    player = Player.objects.filter(user=request.user).first()
    if not player:
        return None
    return player.current_room
