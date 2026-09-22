from django import forms

from .models import Espacio, Movimiento, Reserva
from vehiculos.models import Vehiculo
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


class VehiculoChoiceField(forms.ModelChoiceField):
    """Muestra matrícula + dueño, para que el personal identifique el vehículo."""

    def label_from_instance(self, obj):
        return f"{obj.matricula} — {obj.usuario.nombre} {obj.usuario.apellido}"


class IngresoForm(forms.ModelForm):
    """
    Registrar ingreso de vehículo. Sólo la usan Personal de Estacionamiento
    o Administrador (ver estacionamiento.decorators.personal_requerido), por
    eso permite elegir el vehículo de CUALQUIER usuario registrado, no sólo
    los propios.
    """

    vehiculo = VehiculoChoiceField(
        queryset=Vehiculo.objects.select_related("usuario").order_by(
            "usuario__apellido", "usuario__nombre", "matricula"
        ),
        label="Vehículo",
    )

    class Meta:
        model = Movimiento
        fields = ["vehiculo", "espacio"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["espacio"].queryset = Espacio.objects.filter(
            tipo_estado__nombre_estado="Libre"
        ).select_related("zona")

    def clean(self):
        cleaned_data = super().clean()
        vehiculo = cleaned_data.get("vehiculo")

        if vehiculo and Movimiento.objects.filter(
            vehiculo=vehiculo, fecha_hora_salida__isnull=True
        ).exists():
            raise forms.ValidationError(
                "Ese vehículo ya tiene un ingreso registrado sin salida."
            )

        return cleaned_data