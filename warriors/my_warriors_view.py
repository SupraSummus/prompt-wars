from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.template.response import TemplateResponse

from djsfc import Router, parse_template
from users import google_login

from .models import Arena
from .warriors import Warrior


router = Router(__name__)

WARRIORS_PER_PAGE = 25


template = parse_template('''\
{% extends "base.html" %}

{% block title %}My prompts - Prompt Wars{% endblock %}

{% block main %}
    <h1>My prompts</h1>
    <table>
        <thead>
            <tr>
                <th>Name</th>
                {% for arena in listed_arenas %}
                    <th>{{ arena.name }}</th>
                {% endfor %}
            </tr>
        </thead>
        <tbody>
            {% for warrior in page_obj %}
                <tr>
                    <td>{{ warrior.name }}</td>
                    {% for arena, warrior_arena in warrior.warrior_arena_objects %}
                        <td>
                            {% if warrior_arena %}
                                <a href="{% url 'warrior_detail' warrior_arena.id %}">
                                    {{ arena.name }}
                                </a>
                            {% endif %}
                        </td>
                    {% endfor %}
                </tr>
            {% endfor %}
        </tbody>
    </table>

    {% if page_obj.has_other_pages %}
        <nav class="pagination">
            {% if page_obj.has_previous %}
                <a href="?page=1">&laquo; first</a>
                <a href="?page={{ page_obj.previous_page_number }}">previous</a>
            {% endif %}

            <span class="current">
                Page {{ page_obj.number }} of {{ page_obj.paginator.num_pages }}
            </span>

            {% if page_obj.has_next %}
                <a href="?page={{ page_obj.next_page_number }}">next</a>
                <a href="?page={{ page_obj.paginator.num_pages }}">last &raquo;</a>
            {% endif %}
        </nav>
    {% endif %}

    {% if offer_google_login %}
        <section>
            <h2>Log in with Google</h2>
            <p>Connect a Google account to log in to this one with it, instead of the password.</p>
            <form method="post" action="{% url 'google_login:start' %}">
                {% csrf_token %}
                <input type="hidden" name="next" value="{{ request.get_full_path }}">
                <button type="submit" class="secondary outline">Connect Google</button>
            </form>
        </section>
    {% endif %}
{% endblock %}
''', router=router)


@router.route('GET', '')
@login_required
def index(request):
    listed_arenas = list(Arena.objects.filter(
        listed=True,
    ))
    warriors = Warrior.objects.filter(
        users=request.user,
    ).prefetch_related('warrior_arenas').order_by('name')

    paginator = Paginator(warriors, WARRIORS_PER_PAGE)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    for warrior in page_obj:
        warrior.warrior_arena_objects = get_warrior_arena_objects(warrior, listed_arenas)

    context = {
        'listed_arenas': listed_arenas,
        'page_obj': page_obj,
        # the way an account made with a password gets Google login
        'offer_google_login': google_login.is_enabled() and not request.user.google_accounts.exists(),
    }
    return TemplateResponse(request, template, context)


def get_warrior_arena_objects(warrior, listed_arenas):
    warrior_arena_objects = []
    for arena in listed_arenas:
        warrior_arena = next(
            (wa for wa in warrior.warrior_arenas.all() if wa.arena_id == arena.id),
            None,
        )
        warrior_arena_objects.append((arena, warrior_arena))
    return warrior_arena_objects
