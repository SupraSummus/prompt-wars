import datetime
import uuid

import anthropic
from django.contrib.auth.decorators import permission_required
from django.db import models
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.utils import timezone
from django_goals.models import AllDone, Goal, RetryMeLater, schedule

from djsfc import Router, UnionTemplate, get_template_block, parse_template
from warriors.anthropic import client as anthropic_client


class Chunk(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    previous_chunk = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='next_chunks',
    )
    text = models.TextField()
    generated_goal = models.OneToOneField(
        to=Goal,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='generated_chunk',
    )

    def get_history(self):
        chunks = []
        chunk = self.previous_chunk
        while chunk:
            assert chunk not in chunks  # protect against cycles
            chunks.append(chunk)
            chunk = chunk.previous_chunk
        chunks.reverse()
        return chunks

    def schedule_generate(self):
        self.generated_goal = schedule(ensure_generated)
        self.save(update_fields=['generated_goal'])


CHUNK_SEPARATOR = '\n\n'


def ensure_generated(goal):
    now = timezone.now()
    chunk = goal.generated_chunk
    if chunk.text:
        return AllDone()
    history = chunk.get_history()
    text = CHUNK_SEPARATOR.join(chunk.text for chunk in history)
    messages = [
        {'role': 'user', 'content': '-'},
        {'role': 'assistant', 'content': text},
    ]
    try:
        response = anthropic_client.messages.create(
            model="claude-3-haiku-20240307",
            messages=messages,
            max_tokens=4096,
        )
    except anthropic.RateLimitError:
        return RetryMeLater(precondition_date=now + datetime.timedelta(minutes=5))

    # extract paragraphs from response
    response_text = ''.join(block.text for block in response.content)
    new_chunks = response_text.split(CHUNK_SEPARATOR)
    new_chunks = [t.strip() for t in new_chunks]
    new_chunks = [t for t in new_chunks if t]

    # save the original chunk
    chunk.text, *new_chunks = new_chunks
    chunk.save(update_fields=['text'])

    # and save followups
    for new_chunk_text in new_chunks:
        new_chunk = Chunk.objects.create(
            previous_chunk=chunk,
            text=new_chunk_text,
        )
        chunk = new_chunk

    return AllDone()


router = Router(__name__)
template = parse_template('''\
{% extends 'base.html' %}
{% block main %}
    <div id="history">
        {% for history_chunk in history_chunks %}
            {% block history_chunk %}
                <div hx-swap-oob="beforeend:#history">
                    {% include 'stories/models/chunk_template' with chunk=history_chunk %}
                    <aside style="text-align: right;">
                        <p><small>
                            <a href="{% url ':index' history_chunk.id %}">Continue from this point</a>
                        </small></p>
                    </aside>
                </div>
            {% endblock %}
        {% endfor %}
    </div>
    <hr>
    {% block continuations %}
        <div class="grid" hx-target="this" hx-swap="outerHTML">
            {% for next_chunk in chunk.next_chunks.all %}
                <div>
                    {% include 'stories/models/chunk_template' with chunk=next_chunk %}
                    <button class="outline"
                        hx-get="{% url ':select_chunk' next_chunk.id %}"
                        hx-push-url="{% url ':index' next_chunk.id %}"
                    >Continue this version</button>
                </div>
            {% endfor %}
            <form hx-post="{% url ':create_next' chunk.id %}">
                {% csrf_token %}
                <input type="submit" value="Make up new continuation">
            </form>
        </div>
    {% endblock %}
{% endblock %}
''', router)
history_chunk_template = get_template_block(template, 'history_chunk')
continuations_block = get_template_block(template, 'continuations')


chunk_template = parse_template('''\
{% if chunk.text %}
    <p>{{ chunk.text }}</p>
{% else %}
    <p aria-busy="true"
        hx-get="{% url ':chunk' chunk.id %}"
        hx-trigger="load delay:2s"
        hx-target="this"
        hx-swap="outerHTML"
    >Generating...</p>
{% endif %}
''', router)


@router.route('GET', '<uuid:chunk_id>/')
def index(request, chunk_id):
    chunk = get_chunk(request, chunk_id)
    return TemplateResponse(request, template, {
        'chunk': chunk,
        'history_chunks': chunk.get_history() + [chunk],
    })


@router.route('POST', '<uuid:chunk_id>/create_next/')
@permission_required('stories.add_chunk')
def create_next(request, chunk_id):
    chunk = get_chunk(request, chunk_id)
    next_chunk = Chunk.objects.create(previous_chunk=chunk)
    next_chunk.schedule_generate()
    return TemplateResponse(request, continuations_block, {'chunk': chunk})


@router.route('GET', '<uuid:chunk_id>/chunk/')
def chunk(request, chunk_id):
    chunk = get_chunk(request, chunk_id)
    return TemplateResponse(request, chunk_template, {'chunk': chunk})


@router.route('GET', '<uuid:chunk_id>/select_chunk/')
def select_chunk(request, chunk_id):
    chunk = get_chunk(request, chunk_id)
    return TemplateResponse(
        request,
        UnionTemplate([history_chunk_template, continuations_block]),
        {
            'chunk': chunk,
            'history_chunk': chunk,
        },
    )


def get_chunk(request, chunk_id):
    return get_object_or_404(Chunk, id=chunk_id)
