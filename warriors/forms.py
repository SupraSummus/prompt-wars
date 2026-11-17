from django import forms
from django.utils.translation import gettext as _

from .battles import Battle
from .warriors import Warrior


class ChallengeWarriorForm(forms.Form):
    warrior = forms.ModelChoiceField(
        queryset=Warrior.objects.all(),
        widget=forms.RadioSelect,
        label=_('Choose your prompt'),
    )

    def __init__(self, *args, opponent=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.opponent = opponent
        self.user = user

        self.fields['warrior'].queryset = Warrior.objects.on_ladder().filter(
            users=self.user,
        ).exclude(
            id=self.opponent.id,
        )

    def clean(self):
        if self.errors:
            return
        cleaned_data = super().clean()
        warrior = cleaned_data['warrior']
        earlier_battle = Battle.objects.with_warriors(
            self.opponent.id,
            warrior.id,
        ).recent().exists()
        if earlier_battle:
            self.add_error('warrior', forms.ValidationError(
                _('This battle already happened'),
                code='duplicate',
            ))
        return cleaned_data
