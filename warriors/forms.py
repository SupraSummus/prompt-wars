import hashlib

from django import forms
from django.utils.translation import gettext as _
from django_q.tasks import async_task
from django_recaptcha.fields import ReCaptchaField

from .models import Warrior
from .tasks import do_moderation


class WarriorCreateForm(forms.ModelForm):
    captcha = ReCaptchaField(label='')

    class Meta:
        model = Warrior
        fields = (
            'body',
            'name',
            'author',
            'captcha',
        )
        labels = {
            'body': 'Prompt',
            'name': 'Warrior name (optional)',
            'author': 'Author (optional, but recommended for eternal glory)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_suffix = ''

    def clean_body(self):
        body = self.cleaned_data['body']
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
        warrior.body_sha_256 = self.cleaned_data['body_sha_256']
        assert commit
        warrior.save()
        async_task(do_moderation, warrior.id)
        return warrior
