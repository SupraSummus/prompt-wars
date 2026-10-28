"""
Connect a password account from a Google-only one (`docs/accounts.md`):
the password proves the other account, being logged in proves this one,
and the two become the password account.
"""
import logging

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect
from django.template.response import TemplateResponse

from djsfc import Router, parse_template
from warriors.models import WarriorUserPermission
from warriors.warriors import Warrior

from .models import GoogleAccount


logger = logging.getLogger(__name__)

router = Router(__name__)


template = parse_template('''\
{% extends "registration/auth_base.html" %}

{% block title %}Connect a password account - Prompt Wars{% endblock %}

{% block auth %}
  <hgroup>
    <h1>Connect a password account</h1>
    <p>For an account you made with a password before using Google.</p>
  </hgroup>
  <p>
    Log in to it below.
    It gets this account's prompts, and Google logs you in to it from then on.
    This account, {{ user.username }}, is closed.
  </p>
  <form method="post" action="{% url 'connect_password:connect' %}">
    {% csrf_token %}
    {{ form.as_div }}
    <button type="submit">Connect</button>
  </form>
{% endblock %}
''', router=router)


def offered_to(user):
    """Only a Google-only account: closing a password account would end a login its owner still uses."""
    return not user.has_usable_password()


@router.route('GET', '')
@login_required
def page(request):
    if not offered_to(request.user):
        raise Http404
    return TemplateResponse(request, template, {'form': AuthenticationForm(request)})


@router.route('POST', '')
@login_required
def connect(request):
    if not offered_to(request.user):
        raise Http404
    form = AuthenticationForm(request, data=request.POST)
    if not form.is_valid():
        return TemplateResponse(request, template, {'form': form})
    keep = form.get_user()
    logger.info('Connecting a password account: user %s merges into user %s', request.user.id, keep.id)
    merge_accounts(keep=keep, absorb=request.user)
    login(request, keep)
    messages.success(request, f"Connected: you are logged in as {keep.username}, with Google or the password.")
    return redirect('my_warriors:index')


@transaction.atomic
def merge_accounts(keep, absorb):
    """
    Give `keep` the prompts, authorship and Google login of `absorb`, then close `absorb`.
    Closed, not deleted, so the admin still shows what happened to it.
    A prompt both hold keeps `keep`'s name for it and its choice about public replies.
    """
    held_by_keep = WarriorUserPermission.objects.filter(user=keep).values('warrior')
    held_by_both = list(Warrior.objects.filter(
        id__in=WarriorUserPermission.objects.filter(user=absorb, warrior__in=held_by_keep).values('warrior'),
    ))
    WarriorUserPermission.objects.filter(user=absorb, warrior__in=held_by_keep).delete()
    WarriorUserPermission.objects.filter(user=absorb).update(user=keep)
    for warrior in held_by_both:
        warrior.update_public_battle_results()
    Warrior.objects.filter(created_by=absorb).update(created_by=keep)
    GoogleAccount.objects.filter(user=absorb).update(user=keep)
    absorb.is_active = False
    absorb.save(update_fields=['is_active'])
