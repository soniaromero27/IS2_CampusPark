from django import forms

from .models import Facultad


class FacultadForm(forms.ModelForm):
    class Meta:
        model = Facultad
        fields = ["nombre", "descripcion"]
