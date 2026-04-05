from django import forms
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from dominate.tags import a, button, dd, div, dl, dt, em
from dominate.tags import form as form_tag
from dominate.tags import h1, main, p, strong
from dominate.util import raw

from djsfc import Router, parse_template

from .models import EMBEDDING_BITS, MAX_PHRASE_LENGTH, ExplorerQuery


router = Router(__name__)


class ExplorerForm(forms.ModelForm):
    phrase = forms.CharField(
        label='Phrase',
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter a phrase to explore its embedding...',
            'maxlength': MAX_PHRASE_LENGTH,
        }),
        max_length=MAX_PHRASE_LENGTH,
    )

    class Meta:
        model = ExplorerQuery
        fields = ('phrase',)


base_template = parse_template('''\
{% extends "base.html" %}
{% block title %}{{ page_title }}{% endblock %}
{% block content %}{{ content|safe }}{% endblock %}
''', router=router)


def _render_embedding_status(query):
    """Render embedding status fragment. Pending state polls via htmx."""
    el = div(id="embedding-status")
    if query.embedding:
        el.add(strong("Computed"))
    else:
        el.attributes['hx-get'] = reverse(
            'embedding_explorer:status',
            kwargs={'query_id': query.id},
        )
        el.attributes['hx-trigger'] = 'every 2s'
        el.attributes['hx-swap'] = 'outerHTML'
        el.add(em("Pending computation..."))
    return el


def _build_index_page(form_instance):
    main_el = main(cls="container")
    with main_el:
        h1("Embedding Explorer")
        p(
            "Enter a phrase (up to ", strong(str(MAX_PHRASE_LENGTH)),
            " characters) and we will compute its ",
            strong("voyage-4-large"), " binary embedding (",
            str(EMBEDDING_BITS), " bits).",
        )
        with form_tag(method="post"):
            raw('{% csrf_token %}')
            raw(form_instance.as_div())
            button("Compute Embedding", type="submit")
    return main_el


def _build_detail_page(query):
    main_el = main(cls="container")
    with main_el:
        h1("Embedding Explorer")
        with dl():
            dt("Phrase")
            dd(query.phrase)
            dt("Embedding")
            dd(_render_embedding_status(query))
        p(a(
            "\u2190 Back to explorer",
            href=reverse('embedding_explorer:index_get'),
        ))
    return main_el


@router.route('GET', '')
def index_get(request):
    content = _build_index_page(ExplorerForm())
    return TemplateResponse(request, base_template, {
        'page_title': 'Embedding Explorer - Prompt wars',
        'content': content.render(),
    })


@router.route('POST', '')
def index_post(request):
    form_instance = ExplorerForm(request.POST)
    if form_instance.is_valid():
        query = ExplorerQuery.get_or_create(form_instance.cleaned_data['phrase'])
        return redirect('embedding_explorer:detail', query_id=query.id)
    content = _build_index_page(form_instance)
    return TemplateResponse(request, base_template, {
        'page_title': 'Embedding Explorer - Prompt wars',
        'content': content.render(),
    })


@router.route('GET', '<uuid:query_id>/')
def detail(request, query_id):
    query = get_object_or_404(ExplorerQuery, id=query_id)
    content = _build_detail_page(query)
    return TemplateResponse(request, base_template, {
        'page_title': f'{query.phrase} - Embedding Explorer',
        'content': content.render(),
    })


@router.route('GET', '<uuid:query_id>/status/')
def status(request, query_id):
    """HTMX endpoint returning the embedding status fragment."""
    query = get_object_or_404(ExplorerQuery, id=query_id)
    return HttpResponse(_render_embedding_status(query).render())
