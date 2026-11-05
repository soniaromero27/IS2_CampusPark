from django import forms

from .models import Reglamento, Tarifa


class TarifaForm(forms.ModelForm):
    class Meta:
        model = Tarifa
        fields = ["descripcion", "valor_por_hora", "vigencia", "tipo"]
        widgets = {
            "vigencia": forms.DateInput(attrs={"type": "date"}),
        }


class ReglamentoTextoForm(forms.ModelForm):
    """Editar sólo el texto del reglamento. Sólo Administrador."""

    class Meta:
        model = Reglamento
        fields = ["reglamento"]
        widgets = {
            "reglamento": forms.Textarea(attrs={"rows": 18, "style": "width:100%;"}),
        }


class HorariosForm(forms.ModelForm):
    """Editar sólo la hora de apertura y de cierre. Sólo Administrador."""

    class Meta:
        model = Reglamento
        fields = ["hora_apertura", "hora_cierre", "tolerancia_validacion"]
        widgets = {
            "hora_apertura": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "hora_cierre": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        }
        labels = {"tolerancia_validacion": "Tolerancia para salir tras validar el ticket (minutos)"}

    def clean(self):
        cleaned_data = super().clean()
        hora_apertura = cleaned_data.get("hora_apertura")
        hora_cierre = cleaned_data.get("hora_cierre")
        if hora_apertura and hora_cierre and hora_cierre <= hora_apertura:
            self.add_error(
                "hora_cierre", "La hora de cierre debe ser posterior a la de apertura."
            )
        return cleaned_data