from django import forms
from django.core.exceptions import NON_FIELD_ERRORS
from django.db.models import Max
from django.utils import timezone

from reglas.models import Reglamento
from vehiculos.models import Vehiculo
from .ingreso import analizar_patente

from .models import Espacio, Movimiento, Reserva, Zona, Ticket
from datetime import datetime



class ReservaForm(forms.ModelForm):
    """
    Reservar un espacio. Se elige el día, la hora de inicio y la hora
    de fin; se asume que la reserva termina el mismo día que empieza
    (fecha_inicio y fecha_fin del modelo quedan en ese único día).

    La reserva tiene que quedar dentro del horario de apertura y cierre
    del Reglamento (ver reglas.models.Reglamento). Si todavía no se
    cargó el reglamento, no hay horario definido y no se restringe nada.
    Los ingresos y salidas NO están sujetos a este horario.

    Si se pasa 'usuario', sólo se ofrecen (y se aceptan) espacios de
    zonas que ese usuario puede usar: zonas sin facultad (libres para
    todos) o de su propia facultad. Los usuarios Externos sólo ven
    zonas sin facultad. Ver Zona.permitidas_para.
    """

    fecha = forms.DateField(
        label="Día a reservar", widget=forms.DateInput(attrs={"type": "date"})
    )
    hora_inicio = forms.TimeField(
        label="Hora de inicio",
        widget=forms.TimeInput(
            attrs={"type": "time", "step": 1800, "list": "horas-datalist"}
        ),
        help_text="Podés escribirla a mano o elegirla de la lista (cada 30 minutos).",
    )
    hora_fin = forms.TimeField(
        label="Hora de fin",
        widget=forms.TimeInput(
            attrs={"type": "time", "step": 1800, "list": "horas-datalist"}
        ),
        help_text="Del mismo día. Podés escribirla a mano o elegirla de la lista.",
    )

    class Meta:
        model = Reserva
        fields = ["espacio"]

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        if usuario is not None:
            self.fields["espacio"].queryset = (
                Espacio.objects.filter(zona__in=Zona.permitidas_para(usuario))
                .select_related("zona")
                .order_by("zona__nombre", "numero")
            )

        self.reglamento = Reglamento.objects.first()
        if self.reglamento:
            apertura = self.reglamento.hora_apertura.strftime("%H:%M")
            cierre = self.reglamento.hora_cierre.strftime("%H:%M")
            for campo in ("hora_inicio", "hora_fin"):
                self.fields[campo].widget.attrs.update({"min": apertura, "max": cierre})
            self.fields["hora_inicio"].help_text += (
                f" Horario del estacionamiento: de {apertura} a {cierre} hs."
            )

    def clean(self):
        cleaned_data = super().clean()
        fecha = cleaned_data.get("fecha")
        hora_inicio = cleaned_data.get("hora_inicio")
        hora_fin = cleaned_data.get("hora_fin")
        espacio = cleaned_data.get("espacio")

        if espacio and espacio.tipo_estado.nombre_estado == "Fuera de servicio":
            self.add_error("espacio", "Ese espacio está fuera de servicio.")

        if not (fecha and hora_inicio and hora_fin):
            return cleaned_data

        if hora_fin <= hora_inicio:
            self.add_error(
                "hora_fin", "La hora de fin debe ser posterior a la hora de inicio."
            )
            return cleaned_data

        if self.reglamento:
            apertura = self.reglamento.hora_apertura
            cierre = self.reglamento.hora_cierre
            fuera_de_horario = False
            if hora_inicio < apertura:
                self.add_error(
                    "hora_inicio",
                    f"El estacionamiento abre a las {apertura:%H:%M} hs: no se puede "
                    f"reservar antes de esa hora.",
                )
                fuera_de_horario = True
            if hora_fin > cierre:
                self.add_error(
                    "hora_fin",
                    f"El estacionamiento cierra a las {cierre:%H:%M} hs: la reserva no "
                    f"puede terminar después de esa hora.",
                )
                fuera_de_horario = True
            if fuera_de_horario:
                return cleaned_data

        if fecha < timezone.localdate():
            self.add_error("fecha", "No podés reservar una fecha anterior a hoy.")
            return cleaned_data

        fecha_inicio = datetime.combine(fecha, hora_inicio)
        fecha_fin = datetime.combine(fecha, hora_fin)
        if timezone.is_naive(fecha_inicio):
            fecha_inicio = timezone.make_aware(fecha_inicio)
        if timezone.is_naive(fecha_fin):
            fecha_fin = timezone.make_aware(fecha_fin)

        if fecha_inicio < timezone.now():
            self.add_error(
                "hora_inicio", "No podés reservar un horario que ya pasó."
            )
            return cleaned_data

        # fecha_inicio/fecha_fin no son campos de este form (se calculan
        # acá), así que se asignan directo a la instancia para que
        # self.save() los guarde.
        self.instance.fecha_inicio = fecha_inicio
        self.instance.fecha_fin = fecha_fin

        if espacio:
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
                    "Ese espacio ya tiene una reserva activa que se solapa con ese día/horario."
                )

        return cleaned_data


def _normalizar_patente(valor):
    patente = (valor or "").strip().upper()
    if not patente:
        raise forms.ValidationError("Ingresá una patente válida.")
    if Movimiento.objects.filter(patente=patente, fecha_hora_salida__isnull=True).exists():
        raise forms.ValidationError("Esa patente ya tiene un ingreso registrado sin salida.")
    return patente


class PatenteForm(forms.Form):
    """Paso 1 del ingreso: sólo la chapa."""

    patente = forms.CharField(
        max_length=15,
        label="Chapa / Patente",
        widget=forms.TextInput(
            attrs={"list": "patentes-datalist", "autocomplete": "off", "autofocus": True}
        ),
    )

    def clean_patente(self):
        return _normalizar_patente(self.cleaned_data["patente"])


class IngresoForm(forms.Form):
    """
    Paso 2 del ingreso (sólo Personal o Administrador): elegir el espacio
    para una chapa ya ingresada. Todo se vuelve a validar acá, en el
    servidor, con ingreso.analizar_patente (no se confía en lo que mostró
    la pantalla):

    - Si la chapa tiene reservas vigentes ahora, el espacio tiene que ser
      uno de los reservados; esa reserva queda en self.reserva_activa para
      que la vista la marque 'Confirmada'. Si el espacio elegido está
      Ocupado o Fuera de servicio, se reasigna a otro Libre de la MISMA
      zona (self.reasignado / self.espacio_original); si no hay ninguno,
      es un error.
    - Si no tiene reservas, el espacio tiene que estar Libre y en una zona
      a la que el usuario tenga acceso (una chapa no registrada sólo
      accede a zonas sin facultad).
    """

    patente = forms.CharField(max_length=15, widget=forms.HiddenInput)
    espacio = forms.ModelChoiceField(
        queryset=Espacio.objects.select_related("zona", "tipo_estado"),
        label="Espacio",
        error_messages={"required": "Elegí un espacio."},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reserva_activa = None
        self.reasignado = False
        self.cambio_de_zona = False  # se mantiene por compatibilidad: ya no hay cambio de zona
        self.espacio_original = None

    def clean_patente(self):
        return _normalizar_patente(self.cleaned_data["patente"])

    def clean(self):
        cleaned_data = super().clean()
        patente = cleaned_data.get("patente")
        espacio = cleaned_data.get("espacio")
        if not patente or not espacio:
            return cleaned_data

        analisis = analizar_patente(patente)
        usuario = analisis["usuario"]

        if espacio.pk not in {e.pk for e in analisis["espacios"]}:
            self.add_error("espacio", "Ese espacio no está disponible para esta chapa.")
            return cleaned_data

        if analisis["con_reserva"]:
            self.reserva_activa = analisis["por_espacio"][espacio.pk]
            estado = espacio.tipo_estado.nombre_estado
            if estado not in ("Libre", "Reservado"):
                alternativo = (
                    Espacio.objects.filter(zona=espacio.zona, tipo_estado__nombre_estado="Libre")
                    .exclude(pk=espacio.pk)
                    .select_related("zona", "tipo_estado")
                    .order_by("numero")
                    .first()
                )
                if alternativo is None:
                    self.add_error(
                        "espacio",
                        f"El espacio reservado (N°{espacio.numero}) de la zona '{espacio.zona}' "
                        f"está {estado.lower()} y no hay otro libre en esa zona.",
                    )
                    return cleaned_data
                self.reasignado = True
                self.espacio_original = espacio
                espacio = alternativo
                cleaned_data["espacio"] = espacio

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
    """
    Crear o editar una zona manualmente. Sólo Administrador. La
    facultad es opcional: dejarla en 'Ninguna' crea una zona pública,
    sin restricción de acceso por facultad ni por tipo de usuario (ver
    Zona.permite_a). Si se elige una facultad, además se puede acotar
    a ciertos tipos de usuario (Docente, Estudiante, etc.); dejar esa
    lista vacía permite cualquier tipo de esa facultad. Una zona sin
    facultad no puede tener tipos de usuario cargados.

    Permite indicar de una vez cuántos espacios crear en esa zona: se
    numeran a partir del último número ya usado (o desde 1 si es una
    zona nueva sin espacios todavía). Dejarlo en 0 no crea ninguno.
    """

    cantidad_espacios = forms.IntegerField(
        min_value=0,
        required=False,
        initial=0,
        label="Cantidad de espacios a crear",
        help_text="Se numeran a partir del último número usado en la zona (o desde 1 si es nueva).",
    )

    class Meta:
        model = Zona
        fields = ["nombre", "descripcion", "facultad", "tipos_usuario_permitidos"]
        widgets = {
            "tipos_usuario_permitidos": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["facultad"].empty_label = "Ninguna (zona pública)"
        self.fields["tipos_usuario_permitidos"].required = False
        self.fields["tipos_usuario_permitidos"].help_text = (
            "Opcional. Vacío = cualquier tipo de usuario de la facultad elegida arriba "
            "puede usar la zona. No marques nada acá si la zona no tiene facultad."
        )

    def clean(self):
        cleaned_data = super().clean()
        facultad = cleaned_data.get("facultad")
        tipos = cleaned_data.get("tipos_usuario_permitidos")
        if not facultad and tipos:
            self.add_error(
                "tipos_usuario_permitidos",
                "Una zona sin facultad (pública) no puede tener tipos de usuario asociados.",
            )
        return cleaned_data


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


class EspacioForm(forms.ModelForm):
    """
    Editar un espacio a mano (zona, número y estado). Sólo Administrador.

    No deja cambiarle el estado a un espacio que tiene un vehículo
    estacionado (un Movimiento sin salida): primero hay que registrar la
    salida en "Ingresos y salidas", que además libera el espacio y
    calcula el cobro. Cambiar el estado a mano sin hacer eso dejaría el
    movimiento abierto y el espacio con un estado que no corresponde.
    """

    class Meta:
        model = Espacio
        fields = ["zona", "numero", "tipo_estado"]
        error_messages = {
            NON_FIELD_ERRORS: {
                "unique_together": "Ya existe un espacio con ese número en esa zona.",
            }
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["zona"].queryset = Zona.objects.order_by("nombre")

    def clean(self):
        cleaned_data = super().clean()
        estado = cleaned_data.get("tipo_estado")

        if self.instance.pk and estado and estado.nombre_estado != "Ocupado":
            movimiento = self.instance.movimiento_actual
            if movimiento:
                self.add_error(
                    "tipo_estado",
                    f"Hay un vehículo (patente {movimiento.patente}) estacionado en este "
                    f"espacio: registrá su salida en 'Ingresos y salidas' antes de "
                    f"cambiarle el estado.",
                )

        return cleaned_data

# AGREGAR a estacionamiento/forms.py (y importar Ticket en el from .models import ...)

class TicketPagoForm(forms.Form):
    metodo = forms.ChoiceField(choices=Ticket.Metodo.choices, label="Método de pago")
    
    