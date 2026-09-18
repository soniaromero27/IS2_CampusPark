from django import forms

from .models import Reserva
from datetime import timedelta

class ReservaForm(forms.ModelForm):
    class Meta:
        model = Reserva
        fields = ["espacio", "fecha_inicio", "fecha_fin"]       
        widgets = {
            "fecha_inicio": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "fecha_fin": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        fecha_inicio = cleaned_data.get("fecha_inicio")
        fecha_fin = cleaned_data.get("fecha_fin")
        espacio = cleaned_data.get("espacio")

        if fecha_inicio and fecha_fin and fecha_fin < fecha_inicio:
            raise forms.ValidationError(
                "La fecha de fin no puede ser anterior a la fecha de inicio."
            )

        if espacio and fecha_inicio and fecha_fin:
            solapadas = Reserva.objects.filter(
                espacio=espacio,
                fecha_inicio__lte=fecha_fin,
                fecha_fin__gte=fecha_inicio,
            ).exclude(
                tipo_estado_reserva__nombre_estado_reserva="Cancelada"
            )
            if self.instance.pk:
                solapadas = solapadas.exclude(pk=self.instance.pk)
            if solapadas.exists():
                raise forms.ValidationError(
                    "Ese espacio ya tiene una reserva activa que se solapa con esas fechas."
                )

        return cleaned_data
