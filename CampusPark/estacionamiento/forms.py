from django import forms
from django.db.models import Max
from django.utils import timezone

from vehiculos.models import Vehiculo

from .models import Espacio, Movimiento, Reserva, Zona
from datetime import datetime


class ReservaForm(forms.ModelForm):
    """
    Reservar un espacio. Se elige el día, la hora de inicio y la hora
    de fin; se asume que la reserva termina el mismo día que empieza
    (fecha_inicio y fecha_fin del modelo quedan en ese único día).

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

    def clean(self):
        cleaned_data = super().clean()
        fecha = cleaned_data.get("fecha")
        hora_inicio = cleaned_data.get("hora_inicio")
        hora_fin = cleaned_data.get("hora_fin")
        espacio = cleaned_data.get("espacio")

        if not (fecha and hora_inicio and hora_fin):
            return cleaned_data

        if hora_fin <= hora_inicio:
            self.add_error(
                "hora_fin", "La hora de fin debe ser posterior a la hora de inicio."
            )
            return cleaned_data

        fecha_inicio = datetime.combine(fecha, hora_inicio)
        fecha_fin = datetime.combine(fecha, hora_fin)
        if timezone.is_naive(fecha_inicio):
            fecha_inicio = timezone.make_aware(fecha_inicio)
        if timezone.is_naive(fecha_fin):
            fecha_fin = timezone.make_aware(fecha_fin)

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


class IngresoForm(forms.Form):
    """
    Registrar ingreso de vehículo. Sólo la usan Personal de Estacionamiento
    o Administrador (ver estacionamiento.decorators.personal_requerido).

    El personal ingresa únicamente la patente; la vista se encarga de
    buscar si corresponde a un Vehiculo/Usuario ya registrado. No hace
    falta que el vehículo exista de antemano: si la patente no está
    registrada, el movimiento igual se crea, quedando asociado a un
    usuario "No registrado" (sin crear ningún Vehiculo ni Usuario nuevo).

    Si el dueño del vehículo tiene una reserva vigente AHORA MISMO
    (Pendiente, dentro de su franja horaria), se ignora el espacio
    elegido y se usa el de esa reserva -- queda guardada en
    self.reserva_activa para que la vista la marque 'Confirmada'. Si
    ese espacio ya está ocupado por otro vehículo (por ejemplo porque
    el anterior no salió a tiempo):
      1. Se busca otro espacio libre en la MISMA zona y se reasigna
         ahí automáticamente (self.reasignado = True,
         self.espacio_original guarda el que tenía reservado).
      2. Si no hay NINGÚN otro libre en esa zona, se expulsa al
         vehículo que está ocupando el espacio reservado: su
         Movimiento se cierra con la salida en este mismo momento
         (self.expulsa_movimiento queda con ese Movimiento, para que
         la vista lo cierre y libere la reserva que tuviera), y el
         espacio reservado queda para el dueño de la reserva.
    Si no hay reserva vigente, el espacio pasa a ser obligatorio y se
    elige a mano.
    """

    patente = forms.CharField(
        max_length=15,
        label="Chapa / Patente",
        widget=forms.TextInput(attrs={"list": "patentes-datalist", "autocomplete": "off"}),
    )
    espacio = forms.ModelChoiceField(
        queryset=Espacio.objects.none(),
        label="Espacio",
        required=False,
        help_text="No hace falta elegirlo si el vehículo tiene una reserva vigente ahora: "
        "se usa el espacio reservado automáticamente.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["espacio"].queryset = Espacio.objects.filter(
            tipo_estado__nombre_estado="Libre"
        ).select_related("zona")
        self.reserva_activa = None
        self.reasignado = False
        self.cambio_de_zona = False
        self.espacio_original = None

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

        if not patente:
            return cleaned_data

        vehiculo = (
            Vehiculo.objects.filter(matricula=patente)
            .select_related("usuario", "usuario__tipo")
            .first()
        )
        usuario = vehiculo.usuario if vehiculo else None

        if usuario is not None:
            ahora = timezone.now()
            self.reserva_activa = (
                Reserva.objects.filter(
                    usuario=usuario,
                    fecha_inicio__lte=ahora,
                    fecha_fin__gte=ahora,
                )
                .exclude(
                    tipo_estado_reserva__nombre_estado_reserva__in=[
                        "Cancelada",
                        "Confirmada",
                        "Finalizada",
                    ]
                )
                .select_related("espacio", "espacio__zona", "espacio__tipo_estado")
                .order_by("fecha_inicio")
                .first()
            )

        if self.reserva_activa:
            espacio_reservado = self.reserva_activa.espacio
            espacio_elegido_a_mano = espacio  # lo que vino del campo, antes de pisarlo

            if espacio_reservado.tipo_estado.nombre_estado == "Ocupado":
                # Otro vehículo está en el espacio reservado (por ejemplo,
                # el anterior no salió a tiempo): reasignar a otro espacio
                # libre de la MISMA zona, para no bloquear el ingreso.
                alternativo = (
                    Espacio.objects.filter(
                        zona=espacio_reservado.zona,
                        tipo_estado__nombre_estado="Libre",
                    )
                    .exclude(pk=espacio_reservado.pk)
                    .order_by("numero")
                    .first()
                )
                if alternativo:
                    espacio = alternativo
                    self.reasignado = True
                    self.espacio_original = espacio_reservado
                elif espacio_elegido_a_mano:
                    # No hay lugar en la zona reservada, pero el personal
                    # ya eligió otro espacio a mano (puede ser de otra
                    # zona): se usa ese, sujeto igual al chequeo de
                    # facultad de más abajo.
                    espacio = espacio_elegido_a_mano
                    self.reasignado = True
                    self.cambio_de_zona = True
                    self.espacio_original = espacio_reservado
                else:
                    self.espacio_original = espacio_reservado
                    self.add_error(
                        "espacio",
                        f"El espacio reservado (N°{espacio_reservado.numero}) de la zona "
                        f"'{espacio_reservado.zona}' está ocupado y no hay otro libre ahí. "
                        f"Elegí otro espacio de la lista (puede ser de otra zona) para "
                        f"continuar, o no registres el ingreso si el vehículo se retira "
                        f"del campus.",
                    )
                    espacio = None
            else:
                espacio = espacio_reservado

            cleaned_data["espacio"] = espacio
        elif not espacio:
            self.add_error(
                "espacio",
                "Elegí un espacio (este vehículo no tiene una reserva vigente ahora mismo).",
            )

        if espacio:
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
    sin restricción de acceso por facultad (ver Zona.permite_a).
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
        fields = ["nombre", "descripcion", "facultad"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["facultad"].empty_label = "Ninguna (zona pública)"


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