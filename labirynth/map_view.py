import humanize
from django import forms
from django.contrib.auth.decorators import permission_required
from django.http import Http404
from django.template.response import TemplateResponse

from djsfc import Router, get_template_block, parse_template

from .models import Room


router = Router(__name__)


template_str = """\
{% extends "base.html" %}

{% block content %}<main class="container">
  <hgroup>
    <h1>{{ x }} / {{ y }} / {{ z }} @ {{ zoom_level }}</h1>
    <p>Roughly {{ metric_size }} in diameter</p>
  </hgroup>

  {% block room_detail %}
    <div hx-target="this" hx-swap="innerHTML">
    {% if edit_form %}
      <form hx-post="{% url ':save' zoom_level x y z %}">
        {% csrf_token %}
        {{ edit_form.as_p }}
        <button type="submit">Save</button>
      </form>
    {% else %}
      {% if room %}
        <p>{{ room.prompt }}</p>
      {% endif %}
      <a hx-get="{% url ':edit' zoom_level x y z %}">Edit</a>
    {% endif %}
  {% endblock %}

  <nav><ul>
    {% for link_text, link_url in links.items %}
      <li>
        <a href="{{ link_url }}">{{ link_text }}</a>
      </li>
    {% endfor %}
  </ul></nav>

</main>{% endblock %}
"""
template = parse_template(template_str, router)
room_detail_block = get_template_block(template, 'room_detail')


@router.route('GET', '<signed_int:zoom_level>/<signed_int:x>/<signed_int:y>/<signed_int:z>/')
def root(request, zoom_level, x, y, z):
    room = get_room(zoom_level, x, y, z)
    links = {
        text: router.reverse(request, ':root', **kwargs)
        for text, kwargs in [
            ('zoom in', {'zoom_level': zoom_level - 1, 'x': x * 2, 'y': y * 2, 'z': z * 2}),
            ('zoom out', get_zoomed_out_coords(zoom_level, x, y, z)),
            ('↖', {'zoom_level': zoom_level, 'x': x - 1, 'y': y, 'z': z + 1}),
            ('↑', {'zoom_level': zoom_level, 'x': x, 'y': y - 1, 'z': z + 1}),
            ('↗', {'zoom_level': zoom_level, 'x': x + 1, 'y': y - 1, 'z': z}),
            ('↘', {'zoom_level': zoom_level, 'x': x + 1, 'y': y, 'z': z - 1}),
            ('↓', {'zoom_level': zoom_level, 'x': x, 'y': y + 1, 'z': z - 1}),
            ('↙', {'zoom_level': zoom_level, 'x': x - 1, 'y': y + 1, 'z': z}),
        ]
    }
    context = {
        'zoom_level': zoom_level,
        'x': x,
        'y': y,
        'z': z,
        'metric_size': humanize.metric(2 ** zoom_level, 'm', precision=1),
        'room': room,
        'links': links,
    }
    return TemplateResponse(request, template, context)


def get_zoomed_out_coords(zoom_level, x, y, z):
    x = x // 2
    y = y // 2
    z = z // 2
    d = z + y + x
    assert d in [-1, 0, 1]
    if d:
        if zoom_level % 3 == 0:
            x -= d
        elif zoom_level % 3 == 1:
            y -= d
        else:
            z -= d
    return {'zoom_level': zoom_level + 1, 'x': x, 'y': y, 'z': z}


class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = ['prompt']


@router.route('GET', '<signed_int:zoom_level>/<signed_int:x>/<signed_int:y>/<signed_int:z>/edit/')
def edit(request, zoom_level, x, y, z):
    room = get_room(zoom_level, x, y, z)
    form = RoomForm(instance=room)
    context = {
        'zoom_level': zoom_level,
        'x': x,
        'y': y,
        'z': z,
        'edit_form': form,
    }
    return TemplateResponse(request, room_detail_block, context)


@router.route('POST', '<signed_int:zoom_level>/<signed_int:x>/<signed_int:y>/<signed_int:z>/edit/')
@permission_required('labirynth.change_room')
def save(request, zoom_level, x, y, z):
    room = get_room(zoom_level, x, y, z)
    form = RoomForm(request.POST, instance=room)
    context = {
        'zoom_level': zoom_level,
        'x': x,
        'y': y,
        'z': z,
    }
    if form.is_valid():
        form.save()
        context['room'] = room
    else:
        context['edit_form'] = form
    return TemplateResponse(request, room_detail_block, context)


def get_room(zoom_level, x, y, z):
    if x + y + z != 0:
        raise Http404()
    room = Room.objects.filter(zoom_level=zoom_level, x=x, y=y, z=z).first()
    if room is None:
        room = Room(zoom_level=zoom_level, x=x, y=y, z=z)
    return room
