import hashlib

from django import forms
from django.contrib import messages
from django.utils.text import normalize_newlines
from django.utils.translation import gettext as _
from django.views.generic.edit import CreateView
from django_goals.models import schedule
from django_recaptcha.fields import ReCaptchaField

from .models import WarriorArena, WarriorUserPermission
from .tasks import do_moderation
from .views import ArenaViewMixin
from .warriors import MAX_WARRIOR_LENGTH, Warrior


class WarriorCreateForm(forms.ModelForm):
    body = forms.CharField(
        label='Prompt',
        widget=forms.Textarea(attrs={'rows': 5}),
        strip=False,
    )
    captcha = ReCaptchaField(label='')

    class Meta:
        model = Warrior
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
        warrior = Warrior.objects.filter(
            body_sha_256=self.cleaned_data['body_sha_256'],
        ).first()

        # create the spell if it is unique
        if warrior is None:
            warrior = super().save(commit=False)

            if self.user.is_authenticated:
                warrior.created_by = self.user

            warrior.body_sha_256 = self.cleaned_data['body_sha_256']
            assert commit
            warrior.save()

            schedule(do_moderation, args=[str(warrior.id)])

        # discovery message
        else:
            messages.info(
                self.request,
                _('The spell already existed. You have discovered it and now you have full access to its secrets.'),
            )

        warrior_arena, warrior_arena_created = WarriorArena.objects.get_or_create(
            arena=self.arena,
            warrior=warrior,
        )

        # give the user permission to the spell
        if self.user.is_authenticated:
            perm, perm_created = WarriorUserPermission.objects.get_or_create(
                warrior=warrior,
                user=self.user,
                defaults={
                    'name': self.cleaned_data['name'],
                    'public_battle_results': self.cleaned_data['public_battle_results'],
                },
            )
            warrior.update_public_battle_results()
        else:
            authorized_warriors = self.session.setdefault('authorized_warriors', [])
            if str(warrior_arena.id) not in authorized_warriors:
                authorized_warriors.append(str(warrior_arena.id))
            if str(warrior.id) not in authorized_warriors:
                authorized_warriors.append(str(warrior.id))
            self.session.save()

        return warrior_arena


class WarriorCreateView(ArenaViewMixin, CreateView):
    form_class = WarriorCreateForm
    template_name = 'warriors/warrior_create.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['arena'] = self.arena
        kwargs['user'] = self.request.user
        kwargs['session'] = self.request.session
        kwargs['request'] = self.request
        return kwargs
