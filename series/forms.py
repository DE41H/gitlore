from uuid import UUID

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from series.models import Genre, SeriesVisibility

User = get_user_model()


class SignupForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]


class AccountSettingsForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["username", "email"]


class SeriesForm(forms.Form):
    name = forms.CharField(max_length=255)
    synopsis = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}), required=False)
    visibility = forms.ChoiceField(choices=SeriesVisibility.choices)
    genres = forms.ModelMultipleChoiceField(
        queryset=Genre.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    world_description = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 6}),
        required=False,
        max_length=5000,
        label="World / Setting Description",
    )

    def __init__(self, *args, include_world=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["genres"].queryset = Genre.objects.all().order_by("name")
        if not include_world:
            self.fields.pop("world_description")


class ChapterForm(forms.Form):
    name = forms.CharField(max_length=255)
    prompt = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 6}),
        max_length=10000,
        label="Chapter Prompt",
        help_text="Describe what should happen in this chapter.",
    )


class CharacterForm(forms.Form):
    name = forms.CharField(max_length=255)
    description = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4}),
        max_length=2000,
    )


CharacterFormSet = forms.formset_factory(CharacterForm, extra=0)


class WorldForm(forms.Form):
    description = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 8}),
        max_length=5000,
        label="World Description",
    )


class ReparentForm(forms.Form):
    new_parent_uid = forms.UUIDField()
