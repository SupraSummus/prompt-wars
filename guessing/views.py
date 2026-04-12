from django import forms
from django.contrib.auth.decorators import login_required
from django.db.models import F
from django.http import HttpResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from dominate.tags import a, button, em
from dominate.tags import form as form_tag
from dominate.tags import h1, h2, input_, li, main, p, strong, ul
from dominate.util import raw
from pgvector.django import HammingDistance

from djsfc import Router, parse_template
from embedding_explorer.models import MAX_PHRASE_LENGTH, ExplorerQuery

from .models import Guess, GuessingTarget


router = Router(__name__)

base_template = parse_template('''\
{% extends "base.html" %}
{% block title %}{{ page_title }}{% endblock %}
{% block content %}{{ content|safe }}{% endblock %}
''', router=router)


class GuessForm(forms.Form):
    phrase = forms.CharField(
        label='Your guess',
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter a phrase to guess the secret embedding...',
            'maxlength': MAX_PHRASE_LENGTH,
        }),
        max_length=MAX_PHRASE_LENGTH,
    )


def _annotated_guesses(target, user):
    return (
        Guess.objects
        .filter(target=target, user=user)
        .select_related('query')
        .annotate(distance=HammingDistance('query__embedding', target.embedding))
        .order_by(F('distance').asc(nulls_first=True))
    )


def _render_guess_row(guess):
    li_el = li(id=f'guess-{guess.id}')
    if guess.distance is not None:
        with li_el:
            strong(guess.query.phrase)
            p(f"Distance: {guess.distance}")
    else:
        li_el.attributes['hx-get'] = reverse(
            'guessing:guess_status',
            kwargs={'guess_id': guess.id},
        )
        li_el.attributes['hx-trigger'] = 'every 2s'
        li_el.attributes['hx-swap'] = 'outerHTML'
        with li_el:
            strong(guess.query.phrase)
            em(" — computing distance...")
    return li_el


def _build_detail_page(request, target, form_instance):
    annotated = _annotated_guesses(target, request.user)
    guesses = list(annotated)
    last_guess = annotated.order_by('-created_at').first()

    main_el = main(cls="container")
    with main_el:
        h1(f"Guess the Embedding: {target.name}")
        p(
            "Submit phrases and see how close their embeddings are to the "
            "secret target. Lower distance means a closer match."
        )
        with form_tag(
            method="post",
            action=reverse('guessing:guess_post', kwargs={'target_id': target.id}),
        ):
            input_(type="hidden", name="csrfmiddlewaretoken", value=get_token(request))
            with strong():
                raw(
                    "Don't share any private, secret, or classified information! "
                    f'See <a href="{reverse("data_policy:root")}">Data policy</a>'
                )
            raw(form_instance.as_div())
            button("Submit Guess", type="submit")

        if last_guess is not None:
            h2("Last guess")
            with ul():
                _render_guess_row(last_guess)

        if guesses:
            h2("All guesses")
            with ul():
                for guess in guesses:
                    _render_guess_row(guess)

        p(a(
            "\u2190 Back to guessing targets",
            href=reverse('guessing:guessing_list'),
        ))
    return main_el


@router.route('GET', '')
@login_required
def guessing_list(request):
    targets = GuessingTarget.objects.all()
    main_el = main(cls="container")
    with main_el:
        h1("Embedding Guessing Game")
        p("Try to find phrases whose embeddings are close to the secret targets.")
        if targets:
            with ul():
                for target in targets:
                    with li():
                        a(
                            target.name,
                            href=reverse(
                                'guessing:detail',
                                kwargs={'target_id': target.id},
                            ),
                        )
        else:
            p(em("No active guessing targets at this time."))
    return TemplateResponse(request, base_template, {
        'page_title': 'Embedding Guessing Game - Prompt Wars',
        'content': main_el.render(),
    })


@router.route('GET', '<uuid:target_id>/')
@login_required
def detail(request, target_id):
    target = get_object_or_404(GuessingTarget, id=target_id)
    content = _build_detail_page(request, target, GuessForm())
    return TemplateResponse(request, base_template, {
        'page_title': f'{target.name} - Embedding Guessing Game',
        'content': content.render(),
    })


@router.route('POST', '<uuid:target_id>/')
@login_required
def guess_post(request, target_id):
    target = get_object_or_404(GuessingTarget, id=target_id)
    form = GuessForm(request.POST)
    if form.is_valid():
        query = ExplorerQuery.get_or_create(form.cleaned_data['phrase'])
        Guess.objects.get_or_create(target=target, query=query, user=request.user)
        return redirect('guessing:detail', target_id=target_id)
    content = _build_detail_page(request, target, form)
    return TemplateResponse(request, base_template, {
        'page_title': f'{target.name} - Embedding Guessing Game',
        'content': content.render(),
    })


@router.route('GET', 'guess/<uuid:guess_id>/')
@login_required
def guess_status(request, guess_id):
    guess = get_object_or_404(
        Guess.objects.select_related('query', 'target'),
        id=guess_id,
        user=request.user,
    )
    annotated = _annotated_guesses(guess.target, request.user).get(id=guess_id)
    return HttpResponse(_render_guess_row(annotated).render())
