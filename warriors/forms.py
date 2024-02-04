from django import forms
from django_recaptcha.fields import ReCaptchaField

from .models import Warrior


class WarriorCreateForm(forms.ModelForm):
    captcha = ReCaptchaField()

    class Meta:
        model = Warrior
        fields = (
            'name',
            'author',
            'body',
        )
