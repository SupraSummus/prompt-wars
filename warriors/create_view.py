import hashlib

from django import forms
from django.contrib import messages
from django.utils.text import normalize_newlines
from django.utils.translation import gettext as _
from django.views.generic.edit import CreateView
from django_goals.models import schedule
from django_recaptcha.fields import ReCaptchaField

from .models import (
    MAX_WARRIOR_LENGTH, Arena, WarriorArena, WarriorUserPermission,
)
from .tasks import do_moderation
from .views import ArenaViewMixin
from .warriors import Warrior


class WarriorCreateForm(forms.ModelForm):
    body = forms.CharField(
        label='Prompt',
        widget=forms.Textarea(attrs={'rows': 5}),
        strip=False,
    )
    captcha = ReCaptchaField(label='')

    class Meta:
        model = WarriorArena
        fields = (
            'body',
            'name',
            'author_name',
            'public_battle_results',
            'captcha',
        )
        labels = {
            'name': 'Spell name (optional)',
            'author_name': 'Author (optional, but recommended for eternal glory)',
        }

    def __init__(self, *args, arena=None, user=None, session=None, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_suffix = ''
        self.arena = arena
        self.user = user
        self.session = session
        self.request = request

    def clean_body(self):
        body = self.cleaned_data['body']
        body = normalize_newlines(body)
        if len(body) > MAX_WARRIOR_LENGTH:
            raise forms.ValidationError(
                _('The spell is too long. The maximum length is %(max_length)d characters.') % {
                    'max_length': MAX_WARRIOR_LENGTH,
                },
                code='max_length',
            )

        body_sha_256 = hashlib.sha256(body.encode('utf-8')).digest()
        self.cleaned_data['body_sha_256'] = body_sha_256

        return body

    def save(self, commit=True):
        warrior_arena = WarriorArena.objects.filter(
            arena=self.arena,
            body_sha_256=self.cleaned_data['body_sha_256'],
        ).first()

        # create the spell if it is unique
        if warrior_arena is None:
            warrior_arena = super().save(commit=False)

            warrior_arena.arena = self.arena
            if self.user.is_authenticated:
                warrior_arena.created_by = self.user

            warrior_arena.body_sha_256 = self.cleaned_data['body_sha_256']
            assert commit
            warrior_arena.save()

            schedule(do_moderation, args=[str(warrior_arena.id)])

        # discovery message
        else:
            messages.info(
                self.request,
                _('The spell already existed. You have discovered it and now you have full access to its secrets.'),
            )

        warrior = get_or_create_warrior(warrior_arena)

        # give the user permission to the spell
        if self.user.is_authenticated:
            perm, perm_created = WarriorUserPermission.objects.get_or_create(
                warrior_arena=warrior_arena,
                user=self.user,
                defaults={
                    'warrior': warrior,
                    'name': self.cleaned_data['name'],
                    'public_battle_results': self.cleaned_data['public_battle_results'],
                },
            )
            if not perm.warrior:
                perm.warrior = warrior
                perm.save(update_fields=['warrior'])
            warrior_arena.update_public_battle_results()
        else:
            authorized_warriors = self.session.setdefault('authorized_warriors', [])
            if str(warrior_arena.id) not in authorized_warriors:
                authorized_warriors.append(str(warrior_arena.id))
                self.session.save()

        return warrior_arena


class WarriorCreateView(ArenaViewMixin, CreateView):
    model = WarriorArena
    form_class = WarriorCreateForm
    template_name = 'warriors/warrior_create.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['arena'] = self.arena
        kwargs['user'] = self.request.user
        kwargs['session'] = self.request.session
        kwargs['request'] = self.request
        return kwargs


def get_or_create_warrior(warrior_arena):
    warrior, created = Warrior.objects.get_or_create(
        body_sha_256=warrior_arena.body_sha_256,
        defaults={
            'body': warrior_arena.body,
        },
    )
    meld_warrior(warrior, warrior_arena)
    ensure_warrior_on_all_arenas(warrior)
    return warrior


def ensure_warrior_on_all_arenas(warrior):
    for arena in Arena.objects.filter(listed=True):
        warrior_arena, created = WarriorArena.objects.get_or_create(
            arena=arena,
            body_sha_256=warrior.body_sha_256,
            defaults={
                'warrior': warrior,
                'body': warrior.body,
                'created_at': warrior.created_at,
                'created_by': warrior.created_by,
                'name': warrior.name,
                'author_name': warrior.author_name,
                'moderation_date': warrior.moderation_date,
                'moderation_passed': warrior.moderation_passed,
                'moderation_model': warrior.moderation_model,
                'public_battle_results': warrior.public_battle_results,
            },
        )
        if not created:
            meld_warrior(warrior, warrior_arena)


def meld_warrior(warrior, warrior_arena):
    assert warrior.body_sha_256 == warrior_arena.body_sha_256
    modified = False

    # assign authorship of the oldest instance
    if warrior_arena.created_at < warrior.created_at:
        warrior.created_at = warrior_arena.created_at
        warrior.created_by = warrior_arena.created_by
        warrior.name = warrior_arena.name
        warrior.author_name = warrior_arena.author_name
        modified = True

    # assign most recent moderation data
    if (
        # global warrior not moderated or
        (
            warrior_arena.moderation_passed and
            (warrior.moderation_passed is None)
        ) or
        # we have newer moderation data
        (
            warrior_arena.moderation_date and
            warrior.moderation_date and
            warrior_arena.moderation_date > warrior.moderation_date
        )
    ):
        warrior.moderation_date = warrior_arena.moderation_date
        warrior.moderation_passed = warrior_arena.moderation_passed
        warrior.moderation_model = warrior_arena.moderation_model
        modified = True

    # assign public_battle_results
    if (
        warrior_arena.public_battle_results and
        not warrior.public_battle_results
    ):
        warrior.public_battle_results = warrior_arena.public_battle_results
        modified = True

    if modified:
        warrior.save()

    # link warrior_arena to the warrior
    if warrior_arena.warrior != warrior:
        warrior_arena.warrior = warrior
        warrior_arena.save(update_fields=['warrior'])
