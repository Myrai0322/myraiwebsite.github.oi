"""
Myrai Labs - The Django Forms
"""

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import ContactMessage, QuoteRequest

ALLOWED_EXTENSIONS = ('.pdf', '.doc', '.docx', '.pptx', '.xlsx', '.txt', '.zip')
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024

class CustomUserForm(UserCreationForm):
    """The registration form"""
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].help_text = "Max 150 characters. Letters, digits and @/./+/-/_ only."
        self.fields["username"].widget.attrs.update({"placeholder": "Username"})
        self.fields["email"].widget.attrs.update({"placeholder": "you@example.com"})


class HoneypotMixin:
    """Anti-bot behaviour. Forms that use it must declare the `website`
    field themselves (see QuoteRequestForm / ContactForm)."""

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError("Spam detected.")
        return self.cleaned_data["website"]


def _honeypot_field():
    return forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "class": "hp-field",
            "aria-hidden": "true",
            "tabindex": "-1",
            "autocomplete": "off",
        }),
        label="Leave this field empty",
    )


class QuoteRequestForm(HoneypotMixin, forms.ModelForm):
    website = _honeypot_field()

    class Meta:
        model = QuoteRequest
        fields = [
            "service", "name", "email", "phone", "contact_via_whatsapp",
            "deadline", "budget", "brief", "attachment",
        ]
        widgets = {
            "deadline": forms.DateInput(attrs={"type": "date"}),
            "brief": forms.Textarea(attrs={"rows": 6}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["service"].queryset = self.fields["service"].queryset.select_related("category")
        self.fields["service"].empty_label = "Choose a service…"
        self.fields["budget"].widget.attrs.update({"min": "0", "step": "50", "placeholder": "e.g. 500"})
        self.fields["phone"].widget.attrs.update({"placeholder": "e.g. 071 234 5678 (optional)"})
        for name in ("name", "email"):
            self.fields[name].widget.attrs.update({"class": "required"})

    def clean_attachment(self):
        f = self.cleaned_data.get("attachment")
        if not f:
            return f
        if f.size > MAX_ATTACHMENT_BYTES:
            raise forms.ValidationError("File too large — 2MB max.")
        name = f.name.lower()
        if not name.endswith(ALLOWED_EXTENSIONS):
            raise forms.ValidationError(
                "Allowed file types: PDF, Word, PowerPoint, Excel, TXT or ZIP."
            )
        return f


class ContactForm(HoneypotMixin, forms.ModelForm):
    website = _honeypot_field()

    class Meta:
        model = ContactMessage
        fields = ["name", "email", "message"]
        widgets = {"message": forms.Textarea(attrs={"rows": 6})}


class QuoteStatusLookupForm(forms.Form):
    ref = forms.CharField(max_length=20, label="Order reference", widget=forms.TextInput(attrs={"placeholder": "ML-2026-1234"}))
    email = forms.EmailField(label="Email used on the order")