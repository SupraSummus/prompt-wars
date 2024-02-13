import hashlib

from django import forms
from django.utils.text import normalize_newlines
from django.utils.translation import gettext as _
from django_q.tasks import async_task
from django_recaptcha.fields import ReCaptchaField

from .models import MAX_WARRIOR_LENGTH, Warrior, WarriorUserPermission
from .tasks import do_moderation


class WarriorCreateForm(forms.ModelForm):
    body = forms.CharField(
        label='Prompt',
        widget=forms.Textarea(attrs={'rows': 5}),
        max_length=MAX_WARRIOR_LENGTH,
        strip=False,
    )
    captcha = ReCaptchaField(label='')

    class Meta:
        model = Warrior
        fields = (
            'body',
            'name',
            'author_name',
            'captcha',
        )
        labels = {
            'name': 'Warrior name (optional)',
            'author_name': 'Author (optional, but recommended for eternal glory)',
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_suffix = ''
        self.user = user

    def clean_body(self):
        body = self.cleaned_data['body']
        body = normalize_newlines(body)

        body_sha_256 = hashlib.sha256(body.encode('utf-8')).digest()
        self.cleaned_data['body_sha_256'] = body_sha_256
        if Warrior.objects.filter(body_sha_256=body_sha_256).exists():
            self.add_error('body', forms.ValidationError(
                _('This warrior already exists'),
                code='duplicate',
            ))

        return body

    def save(self, commit=True):
        warrior = super().save(commit=False)

        if self.user.is_authenticated:
            warrior.created_by = self.user

        warrior.body_sha_256 = self.cleaned_data['body_sha_256']
        assert commit
        warrior.save()
        if self.user.is_authenticated:
            WarriorUserPermission.objects.create(
                warrior=warrior,
                user=self.user,
            )
        async_task(do_moderation, warrior.id)
        return warrior
