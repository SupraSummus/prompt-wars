import unicodedata

from django import forms
from django_recaptcha.fields import ReCaptchaField
from django_recaptcha.widgets import ReCaptchaV2Checkbox

from warriors.warriors import MAX_WARRIOR_LENGTH, normalize_warrior_body

from .models import HillAttempt


NAME_MAX_LENGTH = HillAttempt._meta.get_field('display_name').max_length

# Directional formatting characters, which can reorder how the text around a name reads.
_BIDI_CONTROLS = dict.fromkeys(map(ord, (
    '\u202a\u202b\u202c\u202d\u202e'  # embeddings and overrides
    '\u2066\u2067\u2068\u2069'  # isolates
    '\u200e\u200f\u061c'  # marks
)))


def clean_display_text(text):
    """
    A typed name or author, safe to show next to other text.

    Control characters and directional formatting go, so a name can't reverse what follows it;
    zero-width joiners stay, so emoji sequences survive.
    """
    text = ''.join(char for char in text if unicodedata.category(char) != 'Cc')
    return text.translate(_BIDI_CONTROLS).strip()


class HillAttackForm(forms.Form):
    """
    The attack form, which parses the input; the game's rules are `hill.attack.submit_attack`'s.

    The captcha is left out when the attack doesn't need one (`hill.attack.captcha_needed`).
    """
    # the round the page showed, so an attack meant for a boss that has since fallen is caught
    round_number = forms.IntegerField(
        widget=forms.HiddenInput,
    )
    # the `?via=` marker on the link the visitor came by, which `hill.views.attack` counts
    via = forms.CharField(
        widget=forms.HiddenInput,
        required=False,
    )
    body = forms.CharField(
        label='Your prompt',
        widget=forms.Textarea(attrs={'rows': 6}),
        strip=False,
        help_text=f'Up to {MAX_WARRIOR_LENGTH} characters.',
    )
    display_name = forms.CharField(
        label='Name your prompt (optional)',
        max_length=NAME_MAX_LENGTH,
        required=False,
    )
    display_author = forms.CharField(
        label='Author (optional)',
        max_length=NAME_MAX_LENGTH,
        required=False,
    )
    consent = forms.BooleanField(
        label=(
            'I agree that if this prompt takes the hill, '
            "its text, the names I give it and the model's replies will be published."
        ),
        error_messages={'required': 'Agree to the publication terms to attack.'},
    )
    captcha = ReCaptchaField(
        label='',
        # compact: the full-size checkbox is wider than a phone screen
        widget=ReCaptchaV2Checkbox(attrs={'data-size': 'compact'}),
        error_messages={
            'required': "Confirm you're not a robot.",
            'captcha_invalid': "Confirm you're not a robot.",
        },
    )

    def __init__(self, *args, captcha=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_suffix = ''
        if not captcha:
            del self.fields['captcha']

    def clean_body(self):
        body, _ = normalize_warrior_body(self.cleaned_data['body'])
        return body

    def clean_display_name(self):
        return clean_display_text(self.cleaned_data['display_name'])

    def clean_display_author(self):
        return clean_display_text(self.cleaned_data['display_author'])
