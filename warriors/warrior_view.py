from django.shortcuts import redirect
from django.template.response import TemplateResponse

from djsfc import Router, parse_template

from .models import WarriorArena, WarriorUserPermission
from .views import is_request_authorized
from .warriors import Warrior


router = Router(__name__)

template = parse_template('''\
{% extends "base.html" %}

{% block title %}{{ warrior }} - {{ arena.name }}{% endblock %}

{% block content %}
<main class="container">

  <h1>
    {{ warrior }}
    {% if warrior.author_name %}
      <small>by {{ warrior.author_name }}</small>
    {% endif %}
  </h1>

    {% if show_secrets %}
        <details>
            <summary role="button" class="outline">Body</summary>
            {% include 'exact_text.html' with text=warrior.body %}
        </details>
    {% endif %}

    <section>
        <h2>Arenas</h2>
        <table>
            <thead>
                <tr>
                    <th>Arena</th>
                    <th>Rating</th>
                </tr>
            </thead>
            <tbody>
                {% for warrior_arena in warrior_arenas %}
                    <tr>
                        <td>
                            <a href="{% url 'warrior_detail' warrior_arena.id %}">
                                {{ warrior_arena.arena.name }}
                            </a>
                        </td>
                        <td>{{ warrior_arena.rating|default:"-" }}</td>
                    </tr>
                {% endfor %}
            </tbody>
        </table>
    </section>

  {% if warrior_user_permission %}
    <section>
      <h2>Settings</h2>
      <form method="post" action="{% url 'warrior_set_public_battles' warrior.id %}">
        {% csrf_token %}
        <label>
          <input type="checkbox" name="public_battle_results"
            {% if warrior_user_permission.public_battle_results %}checked{% endif %}
          />
          Make battle results public
        </label>
        <input type="submit" value="Save" />
      </form>
    </section>
  {% endif %}

  <section>
    <h2>Details</h2>
    <dl>
      <dt>Created at</dt>
      <dd>{% include 'time.html' with time=warrior.created_at %}</dd>
      <dt>ID</dt>
      <dd><code>{{ warrior.id }}</code></dd>
    </dl>
  </section>
</main>
{% endblock %}
''', router=router)


not_moderated_template = parse_template('''\
{% extends "base.html" %}
{% block content %}
<main class="container">
  <h1>{{ warrior }}</h1>
  {% if warrior.moderation_passed is None %}
    <p>moderation pending</p>
  {% else %}
    <p>moderation failed</p>
  {% endif %}
</main>
{% endblock %}
''', router=router)


@router.route('GET', '<uuid:warrior_id>/')
def get(request, warrior_id):
    try:
        warrior = Warrior.objects.get(id=warrior_id)
    except Warrior.DoesNotExist:
        return redirect('warrior_detail', warrior_id, permanent=True)

    # Get arenas where this warrior exists
    warrior_arenas = WarriorArena.objects.filter(
        warrior=warrior,
    ).select_related('arena')

    # Check if user can see secrets
    show_secrets = is_request_authorized(warrior, request)

    # Get user permissions if authenticated
    warrior_user_permission = None
    if request.user.is_authenticated:
        warrior_user_permission = WarriorUserPermission.objects.filter(
            warrior=warrior,
            user=request.user,
        ).first()

    context = {
        'warrior': warrior,
        'warrior_arenas': warrior_arenas,
        'show_secrets': show_secrets,
        'warrior_user_permission': warrior_user_permission,
    }

    if warrior.moderation_passed:
        _template = template
    else:
        _template = not_moderated_template
    return TemplateResponse(request, _template, context)
