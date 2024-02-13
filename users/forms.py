from django.contrib.auth.forms import UserCreationForm
from django_recaptcha.fields import ReCaptchaField

from .models import User


class SignupForm(UserCreationForm):
    captcha = ReCaptchaField(label='')

    class Meta:
        model = User
        fields = (
            'username',
            'password1',
            'password2',
            'captcha',
        )
