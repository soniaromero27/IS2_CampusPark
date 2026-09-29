from django import forms
from django.db.models import Max

from vehiculos.models import Vehiculo

from .models import Espacio, Movimiento, Reserva, Zona
from datetime import timedelta


class ReservaForm(forms.ModelForm):
    """
    Reservar un espacio. Si se pasa 'usuario', sólo se ofrecen (y se
    aceptan) espacios de zonas que ese usuario puede usar: zonas sin
    facultad (libres para todos) o de su propia facultad. Los usuarios
    Externos sólo ven zonas sin facultad. Ver Zona.permitidas_para.
    """

    class Meta:
        model = Reserva
        fields = ["espacio", "fecha_inicio", "fecha_fin"]
        widgets = {
            "fecha_inicio": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "fecha_fin": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        if usuario is not None:
            self.fields["espacio"].queryset = (
                Espacio.objects.filter(zona__in=Zona.permitidas_para(usuario))
                .select_related("zona")
                .order_by("zona__nombre", "numero")
            )

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


class IngresoForm(forms.Form):
    """
    Registrar ingreso de vehículo. Sólo la usan Personal de Estacionamiento
    o Administrador (ver estacionamiento.decorators.personal_requerido).

    El personal ingresa únicamente la patente; la vista se encarga de
    buscar si corresponde a un Vehiculo/Usuario ya registrado. No hace
    falta que el vehículo exista de antemano: si la patente no está
    registrada, el movimiento igual se crea, quedando asociado a un
    usuario "Desconocido" (sin crear ningún Vehiculo ni Usuario nuevo).
    """

    patente = forms.CharField(
        max_length=15,
        label="Chapa / Patente",
        widget=forms.TextInput(attrs={"list": "patentes-datalist", "autocomplete": "off"}),
    )
    espacio = forms.ModelChoiceField(queryset=Espacio.objects.none(), label="Espacio")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["espacio"].queryset = Espacio.objects.filter(
            tipo_estado__nombre_estado="Libre"
        ).select_related("zona")

    def clean_patente(self):
        patente = self.cleaned_data["patente"].strip().upper()
        if not patente:
            raise forms.ValidationError("Ingresá una patente válida.")
        return patente

    def clean(self):
        cleaned_data = super().clean()
        patente = cleaned_data.get("patente")
        espacio = cleaned_data.get("espacio")

        if patente and Movimiento.objects.filter(
            patente=patente, fecha_hora_salida__isnull=True
        ).exists():
            raise forms.ValidationError(
                "Esa patente ya tiene un ingreso registrado sin salida."
            )

        if patente and espacio:
            vehiculo = (
                Vehiculo.objects.filter(matricula=patente)
                .select_related("usuario", "usuario__tipo")
                .first()
            )
            usuario = vehiculo.usuario if vehiculo else None
            zona = espacio.zona

            if not zona.permite_a(usuario):
                if usuario is None:
                    msg = (
                        f"La patente {patente} no está registrada, por lo que sólo puede "
                        f"estacionar en zonas sin facultad. La zona '{zona}' pertenece a "
                        f"la facultad {zona.facultad}."
                    )
                elif usuario.es_externo:
                    msg = (
                        f"{usuario.nombre} {usuario.apellido} es usuario Externo: sólo puede "
                        f"estacionar en zonas sin facultad. La zona '{zona}' pertenece a "
                        f"la facultad {zona.facultad}."
                    )
                else:
                    msg = (
                        f"{usuario.nombre} {usuario.apellido} no puede estacionar en la zona "
                        f"'{zona}': pertenece a la facultad {zona.facultad}."
                    )
                self.add_error("espacio", msg)

        return cleaned_data


class ZonaForm(forms.ModelForm):
    """Crear una zona manualmente. Sólo Administrador."""

    class Meta:
        model = Zona
        fields = ["nombre", "descripcion", "facultad"]


class EspaciosForm(forms.Form):
    """
    Crear varios espacios de una zona, indicando cuántos (cantidad).
    Sólo Administrador. Si no se indica 'numero_inicial', continúa
    después del último número ya usado en esa zona.
    """

    zona = forms.ModelChoiceField(queryset=Zona.objects.all(), label="Zona")
    cantidad = forms.IntegerField(min_value=1, label="Cantidad de espacios a crear")
    numero_inicial = forms.IntegerField(
        min_value=1,
        required=False,
        label="Número inicial (opcional)",
        help_text="Si lo dejás vacío, se continúa después del último número usado en la zona.",
    )

    def clean(self):
        cleaned_data = super().clean()
        zona = cleaned_data.get("zona")
        cantidad = cleaned_data.get("cantidad")
        numero_inicial = cleaned_data.get("numero_inicial")

        if zona and cantidad:
            if not numero_inicial:
                ultimo = Espacio.objects.filter(zona=zona).aggregate(Max("numero"))["numero__max"] or 0
                numero_inicial = ultimo + 1
                cleaned_data["numero_inicial"] = numero_inicial

            rango = range(numero_inicial, numero_inicial + cantidad)
            existentes = list(
                Espacio.objects.filter(zona=zona, numero__in=rango).values_list("numero", flat=True)
            )
            if existentes:
                numeros = ", ".join(str(n) for n in sorted(existentes))
                raise forms.ValidationError(
                    f"Ya existen espacios con esos números en la zona '{zona}': {numeros}."
                )

        return cleaned_data