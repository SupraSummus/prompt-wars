from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.template.response import TemplateResponse

from djsfc import Router, parse_template
from users import connect_password, google_login

from .rankings import Ranking
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
                {% for ranking in rankings %}
                    <th>{{ ranking.label }}</th>
                {% endfor %}
            </tr>
        </thead>
        <tbody>
            {% for warrior in page_obj %}
                <tr>
                    <td><a href="{{ warrior.get_absolute_url }}">{{ warrior }}</a></td>
                    {% for ranking, rating in warrior.ranking_ratings %}
                        <td>
                            {% if rating %}
                                <a href="{{ rating.get_absolute_url }}">{{ rating.rating|floatformat:0 }}</a>
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

    {% if offer_connect_password %}
        <section>
            <h2>Have a password account too?</h2>
            <p>Connect it to bring its prompts and this account's together, and log in to it with Google.</p>
            <a href="{% url 'connect_password:page' %}" role="button" class="secondary outline">Connect a password account</a>
        </section>
    {% endif %}
{% endblock %}
''', router=router)


@router.route('GET', '')
@login_required
def index(request):
    warriors = Warrior.objects.filter(
        users=request.user,
    ).prefetch_related('ratings').order_by('name')

    paginator = Paginator(warriors, WARRIORS_PER_PAGE)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    for warrior in page_obj:
        ratings = {rating.ranking: rating for rating in warrior.ratings.all()}
        warrior.ranking_ratings = [(ranking, ratings.get(ranking)) for ranking in Ranking]

    context = {
        'rankings': list(Ranking),
        'page_obj': page_obj,
        # the way an account made with a password gets Google login
        'offer_google_login': google_login.is_enabled() and not request.user.google_accounts.exists(),
        # the way out for someone who made a second account by logging in with Google first
        'offer_connect_password': connect_password.offered_to(request.user),
    }
    return TemplateResponse(request, template, context)
