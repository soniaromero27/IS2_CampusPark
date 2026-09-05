from django import forms

from .models import Vehiculo


class VehiculoForm(forms.ModelForm):
    class Meta:
        model = Vehiculo
        fields = ["matricula", "marca", "modelo", "color"]

    def clean_matricula(self):
        matricula = self.cleaned_data["matricula"].upper().strip()
        if Vehiculo.objects.filter(matricula=matricula).exists():
            raise forms.ValidationError("Ya existe un vehículo registrado con esa matrícula.")
        return matricula
