from django import forms

from .models import Reglamento, Tarifa


class TarifaForm(forms.ModelForm):
    class Meta:
        model = Tarifa
        fields = ["descripcion", "valor_por_hora", "vigencia", "tipo"]
        widgets = {
            "vigencia": forms.DateInput(attrs={"type": "date"}),
        }


class ReglamentoForm(forms.ModelForm):
    """Crear o editar el reglamento. Sólo Administrador."""

    class Meta:
        model = Reglamento
        fields = ["reglamento", "hora_apertura", "hora_cierre"]
        widgets = {
            "reglamento": forms.Textarea(attrs={"rows": 10}),
            "hora_apertura": forms.TimeInput(attrs={"type": "time"}),
            "hora_cierre": forms.TimeInput(attrs={"type": "time"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        hora_apertura = cleaned_data.get("hora_apertura")
        hora_cierre = cleaned_data.get("hora_cierre")
        if hora_apertura and hora_cierre and hora_cierre <= hora_apertura:
            self.add_error(
                "hora_cierre", "La hora de cierre debe ser posterior a la de apertura."
            )
        return cleaned_data