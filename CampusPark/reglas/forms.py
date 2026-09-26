from django import forms

from .models import Tarifa


class TarifaForm(forms.ModelForm):
    class Meta:
        model = Tarifa
        fields = ["descripcion", "valor_por_hora", "vigencia", "tipo"]
        widgets = {
            "vigencia": forms.DateInput(attrs={"type": "date"}),
        }
