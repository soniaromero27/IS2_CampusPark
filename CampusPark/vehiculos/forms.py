from django import forms

from .models import Vehiculo


class VehiculoForm(forms.ModelForm):
    class Meta:
        model = Vehiculo
        fields = [
            "matricula",
            "tipo_vehiculo",
            "cedula_verde",
            "marca",
            "modelo",
            "color",
            "anho",
            "chassis",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            # Una vez creado el vehículo, la matrícula no se puede cambiar.
            # 'disabled' no es sólo visual: Django ignora lo que llegue en el
            # POST y conserva el valor guardado.
            self.fields["matricula"].disabled = True
            self.fields["matricula"].help_text = "La matrícula no se puede modificar."

    def clean_matricula(self):
        matricula = self.cleaned_data["matricula"].upper().strip()
        otros = Vehiculo.objects.filter(matricula=matricula)
        if self.instance.pk:  # editando: no cuenta el propio vehículo
            otros = otros.exclude(pk=self.instance.pk)
        if otros.exists():
            raise forms.ValidationError("Ya existe un vehículo registrado con esa matrícula.")
        return matricula