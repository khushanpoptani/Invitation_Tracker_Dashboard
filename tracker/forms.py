from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from .models import MessageType

User = get_user_model()


class BootstrapFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing_class = field.widget.attrs.get("class", "")
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = f"{existing_class} form-check-input".strip()
            else:
                field.widget.attrs["class"] = f"{existing_class} form-control".strip()


class UserFilterForm(BootstrapFormMixin, forms.Form):
    user = forms.ModelChoiceField(queryset=User.objects.filter(is_active=True), required=False)


class MessageTypeForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = MessageType
        fields = ["message_id", "message", "user"]
        widgets = {
            "message": forms.Textarea(attrs={"rows": 3}),
        }


class MessageTypeCreateForm(BootstrapFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["user"].queryset = User.objects.filter(is_active=True).order_by("username")

    class Meta:
        model = MessageType
        fields = ["user", "message"]
        widgets = {
            "message": forms.Textarea(attrs={"rows": 4}),
        }


class CSVUploadForm(BootstrapFormMixin, forms.Form):
    user = forms.ModelChoiceField(queryset=User.objects.filter(is_active=True), required=True)
    csv_file = forms.FileField(required=True)


class StatusSearchForm(BootstrapFormMixin, forms.Form):
    user = forms.ModelChoiceField(queryset=User.objects.filter(is_active=True), required=True)
    name = forms.CharField(max_length=255, required=True)


class TrackerUserCreateForm(BootstrapFormMixin, UserCreationForm):
    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email"]


class TrackerUserUpdateForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "is_active", "is_staff"]
