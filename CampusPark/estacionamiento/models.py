from django.db import models
from django.utils import timezone
import math

from datetime import timedelta
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Sum

from universidad.models import Facultad
from usuarios.models import TipoUsuario, Usuario
from vehiculos.models import Vehiculo


class Zona(models.Model):
    """Entidad 'zona' del DER (HU04 - Gestionar zonas de estacionamiento)."""
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.CharField(max_length=255, blank=True)
    facultad = models.ForeignKey(
        Facultad,
        on_delete=models.PROTECT,
        related_name="zonas",
        null=True,
        blank=True,
        help_text="Dejar en 'Ninguna' para que sea una zona pública, sin restricción de facultad.",
    )
    tipos_usuario_permitidos = models.ManyToManyField(
        TipoUsuario,
        related_name="zonas_permitidas",
        blank=True,
        help_text="Tipos de usuario (Docente, Estudiante, etc.) que pueden usar esta zona, "
        "dentro de los que pertenecen a la facultad de arriba. Vacío = cualquier tipo de "
        "esa facultad puede entrar. Sin sentido (y no permitido) en una zona sin facultad.",
    )

    class Meta:
        verbose_name = "Zona"
        verbose_name_plural = "Zonas"

    def __str__(self):
        return self.nombre

    @classmethod
    def permitidas_para(cls, usuario):
        """
        Zonas que un usuario puede usar (para reservar o estacionar):
        - Zonas sin facultad (facultad nula): libres para todos.
        - Zonas con facultad: sólo para usuarios de esa misma facultad,
          y además -si la zona tiene tipos_usuario_permitidos cargados-
          sólo si el tipo del usuario (Docente, Estudiante, etc.) está
          entre esos tipos. Si la zona no tiene ningún tipo cargado,
          cualquier tipo de esa facultad puede entrar.
        - usuario=None (patente no registrada) o usuario Externo (nunca
          tiene facultad): sólo las zonas sin facultad.
        """
        libres = models.Q(facultad__isnull=True)
        if usuario is None or usuario.es_externo or usuario.facultad_id is None:
            return cls.objects.filter(libres)
        propias = models.Q(facultad_id=usuario.facultad_id) & (
            models.Q(tipos_usuario_permitidos__isnull=True)
            | models.Q(tipos_usuario_permitidos=usuario.tipo_id)
        )
        return cls.objects.filter(libres | propias).distinct()

    def permite_a(self, usuario):
        """True si 'usuario' (o None = no registrado) puede usar esta zona."""
        if self.facultad_id is None:
            return True
        if usuario is None or usuario.es_externo:
            return False
        if usuario.facultad_id != self.facultad_id:
            return False
        tipos_permitidos = self.tipos_usuario_permitidos.all()
        if not tipos_permitidos.exists():
            return True
        return tipos_permitidos.filter(pk=usuario.tipo_id).exists()


class TipoEstado(models.Model):
    """
    Entidad 'tipo_estado' del DER: catálogo de estados posibles de un
    espacio (Libre, Ocupado, Reservado, Fuera de servicio, etc.).
    """
    nombre_estado = models.CharField(max_length=50, unique=True)

    class Meta:
        verbose_name = "Tipo de estado (espacio)"
        verbose_name_plural = "Tipos de estado (espacio)"

    def __str__(self):
        return self.nombre_estado


class Espacio(models.Model):
    """Entidad 'espacio' del DER."""
    numero = models.IntegerField()

    zona = models.ForeignKey(Zona, on_delete=models.CASCADE, related_name="espacios")
    tipo_estado = models.ForeignKey(
        TipoEstado, on_delete=models.PROTECT, related_name="espacios"
    )

    class Meta:
        verbose_name = "Espacio"
        verbose_name_plural = "Espacios"
        unique_together = ("zona", "numero")

    def __str__(self):
        return f"{self.zona} - N°{self.numero}"

    @property
    def movimiento_actual(self):
        """
        El Movimiento sin fecha_hora_salida en este espacio ahora mismo
        (el vehículo que está estacionado ahí), si lo hay.

        Si la consulta precargó los movimientos abiertos en
        'movimientos_abiertos' (ver estacionamiento.views.lista_espacios_view),
        se usan esos y no se hace una consulta por cada espacio.
        """
        abiertos = getattr(self, "movimientos_abiertos", None)
        if abiertos is not None:
            return abiertos[0] if abiertos else None
        return self.movimientos.filter(fecha_hora_salida__isnull=True).first()


class TipoEstadoReserva(models.Model):
    """Entidad 'tipo_estado_reserva' del DER (Pendiente, Confirmada, etc.)."""
    nombre_estado_reserva = models.CharField(max_length=50, unique=True)

    class Meta:
        verbose_name = "Tipo de estado (reserva)"
        verbose_name_plural = "Tipos de estado (reserva)"

    def __str__(self):
        return self.nombre_estado_reserva


class Reserva(models.Model):
    """Entidad 'reserva' del DER."""
    fecha_inicio = models.DateTimeField()
    fecha_fin = models.DateTimeField()
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="reservas")
    espacio = models.ForeignKey(Espacio, on_delete=models.CASCADE, related_name="reservas")
    tipo_estado_reserva = models.ForeignKey(
        TipoEstadoReserva, on_delete=models.PROTECT, related_name="reservas"
    )

    class Meta:
        verbose_name = "Reserva"
        verbose_name_plural = "Reservas"

    def __str__(self):
        return f"Reserva #{self.id} - {self.usuario} - {self.espacio}"


class Movimiento(models.Model):
    """
    Entidad 'movimiento' del DER. El DER tipa fecha_hora_ingreso y
    fecha_hora_salida como DATE; se implementan como DateTimeField
    porque el sistema necesita registrar la hora exacta de ingreso y
    salida para poder calcular el cobro por hora (ver Tarifa).

    El personal de estacionamiento registra el movimiento ingresando
    sólo la patente. 'patente' guarda siempre lo tipeado, exista o no
    un Vehiculo registrado con esa matrícula. Si existe, se linkea en
    'vehiculo' (y de ahí se conoce el usuario dueño); si no existe,
    'vehiculo' queda en null y el movimiento se considera de un
    usuario "Desconocido", sin crear ningún Vehiculo ni Usuario nuevo.
    """
    fecha_hora_ingreso = models.DateTimeField()
    fecha_hora_salida = models.DateTimeField(null=True, blank=True)
    patente = models.CharField(max_length=15)
    vehiculo = models.ForeignKey(
        Vehiculo,
        on_delete=models.SET_NULL,
        related_name="movimientos",
        null=True,
        blank=True,
    )
    
    validado_en = models.DateTimeField(null=True, blank=True)
    validado_hasta = models.DateTimeField(
        null=True, blank=True,
        help_text="Hasta cuándo puede salir sin que se recalcule el cobro (tolerancia tras validar).",
    )
    
    espacio = models.ForeignKey(Espacio, on_delete=models.CASCADE, related_name="movimientos")

    class Meta:
        verbose_name = "Movimiento"
        verbose_name_plural = "Movimientos"

    def __str__(self):
        return f"Movimiento #{self.id} - {self.patente}"

    @property
    def usuario_nombre(self):
        """Nombre del dueño si la patente está registrada, si no 'No registrado'."""
        if self.vehiculo_id and self.vehiculo.usuario_id:
            return f"{self.vehiculo.usuario.nombre} {self.vehiculo.usuario.apellido}"
        return "No registrado"

    def calcular_cobro(self, hasta=None):
        """
        Calcula el monto a cobrar según la tarifa vigente para el tipo
        de usuario dueño del vehículo. Si la patente no está registrada
        (o no tiene usuario asociado), se cobra como tipo 'Externo'.

        Usa fecha_hora_salida si ya está cargada, o timezone.now() como
        estimación (para mostrar un monto antes de confirmar la salida).
        Las horas se redondean hacia arriba, con un mínimo de 1 hora.

        Devuelve un dict: {"tipo", "horas", "tarifa", "monto"}.
        'tarifa' y 'monto' quedan en None si no hay ninguna tarifa
        configurada (con vigencia <= la fecha de salida) para ese tipo.

        Costo de TODA la estadía hasta `hasta` (o la salida, o ahora)."""
        
        from reglas.models import Tarifa
        from usuarios.models import TipoUsuario
 
        if self.vehiculo_id and self.vehiculo.usuario_id:
            tipo = self.vehiculo.usuario.tipo
        else:
            tipo = TipoUsuario.objects.filter(nombre__iexact="Externo").first()
 
        fin = hasta or self.fecha_hora_salida or timezone.now()
        segundos = (fin - self.fecha_hora_ingreso).total_seconds()
        horas = max(1, math.ceil(segundos / 3600))
 
        tarifa = None
        if tipo is not None:
            tarifa = (
                Tarifa.objects.filter(tipo=tipo, vigencia__lte=fin.date())
                .order_by("-vigencia")
                .first()
            )
 
        monto = tarifa.valor_por_hora * horas if tarifa else None
        return {"tipo": tipo, "horas": horas, "tarifa": tarifa, "monto": monto}


    def total_pagado(self):
        """Todo lo abonado hasta ahora por esta estadía (validaciones + pago en la salida)."""
        return self.pagos.aggregate(t=Sum("monto"))["t"] or 0
 
    def cobro_vigente(self, momento=None):
        """
        Cuenta de la estadía al `momento` (por defecto: la salida, o ahora).
 
        - Si está VALIDADO (momento <= validado_hasta): no se recalcula nada;
          se queda con lo ya pagado y no hay nada más que cobrar.
        - Si no (nunca se validó, o la validación VENCIÓ): se cobra toda la
          estadía acumulada desde el ingreso, menos lo ya pagado (el excedente).
 
        Devuelve el dict de calcular_cobro() más:
          pagado, validado, monto_final (total de la estadía) y a_pagar (excedente).
        'monto_final' y 'a_pagar' son None si no hay tarifa.
        """
        momento = momento or self.fecha_hora_salida or timezone.now()
        pagado = self.total_pagado()
        validado = bool(
            self.validado_en and self.validado_hasta and momento <= self.validado_hasta
        )
        cobro = self.calcular_cobro(hasta=self.validado_en if validado else momento)
 
        if cobro["tarifa"] is None:
            total, a_pagar = None, None
        elif validado:
            total, a_pagar = pagado, 0
        else:
            total = cobro["monto"]
            a_pagar = max(0, round(total - pagado, 2))
 
        cobro.update(pagado=pagado, validado=validado, monto_final=total, a_pagar=a_pagar)
        return cobro
 
    def validar(self, metodo, registrado_por):
        """
        Cobra el excedente (si lo hay), y abre la ventana de tolerancia para
        salir (ver Reglamento.tolerancia_validacion). Devuelve lo cobrado.
        Llamar dentro de transaction.atomic() y con el movimiento bloqueado.
        """
        from reglas.models import Reglamento
 
        if self.fecha_hora_salida:
            raise ValidationError("Este vehículo ya registró su salida.")
        ahora = timezone.now()
        cuenta = self.cobro_vigente(momento=ahora)
        if cuenta["tarifa"] is None:
            raise ValidationError("No hay una tarifa configurada para este tipo de usuario.")
        if cuenta["validado"]:
            raise ValidationError(
                "El ticket ya está validado hasta las "
                f"{timezone.localtime(self.validado_hasta):%H:%M} hs."
            )
 
        a_pagar = cuenta["a_pagar"]
        if a_pagar > 0:
            Pago.objects.create(
                movimiento=self, monto=a_pagar, metodo=metodo,
                origen=Pago.Origen.VALIDACION, fecha_pago=ahora,
                registrado_por=registrado_por,
            )
        self.validado_en = ahora
        self.validado_hasta = ahora + timedelta(minutes=Reglamento.tolerancia_actual())
        self.save(update_fields=["validado_en", "validado_hasta"])
        return a_pagar


class Ticket(models.Model):
    """
    Ticket de salida: se emite al registrar la salida de un vehículo y
    guarda una "foto" del cobro (tarifa, horas, monto) por si después
    cambian las tarifas o se borra el vehículo. Incluye el estado de pago.
    """

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente de pago"
        PAGADO = "pagado", "Pagado"
        SIN_CARGO = "sin_cargo", "Sin cargo (validado)"
        SIN_TARIFA = "sin_tarifa", "Sin tarifa configurada"

    class Metodo(models.TextChoices):
        EFECTIVO = "efectivo", "Efectivo"
        TRANSFERENCIA = "transferencia", "Transacción bancaria"
        CREDITO = "credito", "Crédito"

    movimiento = models.OneToOneField(
        Movimiento, on_delete=models.PROTECT, related_name="ticket"
    )
    usuario = models.ForeignKey(
        Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name="tickets",
        help_text="Dueño del vehículo al momento de la salida (vacío = no registrado).",
    )
    patente = models.CharField(max_length=15)
    tipo_usuario = models.CharField(max_length=50, blank=True)

    tarifa = models.ForeignKey(
        "reglas.Tarifa", on_delete=models.SET_NULL, null=True, blank=True, related_name="tickets"
    )
    tarifa_descripcion = models.CharField(max_length=255, blank=True)
    valor_por_hora = models.FloatField(null=True, blank=True)
    horas = models.PositiveIntegerField()
    monto = models.FloatField(null=True, blank=True)

    fecha_ingreso = models.DateTimeField()
    fecha_salida = models.DateTimeField()
    fecha_emision = models.DateTimeField(auto_now_add=True)

    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.PENDIENTE)
    metodo_pago = models.CharField(max_length=20, choices=Metodo.choices, blank=True)
    fecha_pago = models.DateTimeField(null=True, blank=True)
    cobrado_por = models.ForeignKey(
        Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name="tickets_cobrados"
    )
    
    monto_pagado_previo = models.FloatField(
        default=0, help_text="Lo que el usuario ya había pagado (validaciones) antes de salir."
    )

    class Meta:
        verbose_name = "Ticket"
        verbose_name_plural = "Tickets"
        ordering = ["-fecha_emision"]

    def __str__(self):
        return f"{self.numero} - {self.patente}"

    @property
    def numero(self):
        return f"T-{self.pk:06d}" if self.pk else "T-?"

    @property
    def monto_a_cobrar(self):
        """Excedente que falta cobrar en la salida (monto total - pagado antes)."""
        if self.monto is None:
            return None
        return max(0, round(self.monto - (self.monto_pagado_previo or 0), 2))
        

    @classmethod
    def emitir(cls, movimiento, cuenta, validado_por=None):
        """
        Crea (una vez por movimiento) el ticket de salida a partir de
        Movimiento.cobro_vigente(). Estados:
        - sin tarifa                      -> SIN_TARIFA
        - total 0                         -> SIN_CARGO (validado al instante)
        - nada que cobrar (ya pagó antes) -> PAGADO
        - hay excedente                   -> PENDIENTE (lo cobra el personal)
        """
        usuario = None
        if movimiento.vehiculo_id and movimiento.vehiculo.usuario_id:
            usuario = movimiento.vehiculo.usuario
        tarifa = cuenta["tarifa"]
        monto = cuenta["monto_final"]
 
        extra = {}
        if tarifa is None:
            estado = cls.Estado.SIN_TARIFA
        elif monto == 0:
            estado = cls.Estado.SIN_CARGO
            extra = {"fecha_pago": timezone.now(), "cobrado_por": validado_por}
        elif cuenta["a_pagar"] == 0:
            estado = cls.Estado.PAGADO
            ultimo = movimiento.pagos.order_by("-fecha_pago").first()
            if ultimo:
                extra = {
                    "metodo_pago": ultimo.metodo,
                    "fecha_pago": ultimo.fecha_pago,
                    "cobrado_por": ultimo.registrado_por,
                }
        else:
            estado = cls.Estado.PENDIENTE
 
        ticket, _ = cls.objects.get_or_create(
            movimiento=movimiento,
            defaults={
                "usuario": usuario,
                "patente": movimiento.patente,
                "tipo_usuario": str(cuenta["tipo"]) if cuenta["tipo"] else "",
                "tarifa": tarifa,
                "tarifa_descripcion": tarifa.descripcion if tarifa else "",
                "valor_por_hora": tarifa.valor_por_hora if tarifa else None,
                "horas": cuenta["horas"],
                "monto": monto,
                "monto_pagado_previo": cuenta["pagado"],
                "fecha_ingreso": movimiento.fecha_hora_ingreso,
                "fecha_salida": movimiento.fecha_hora_salida,
                "estado": estado,
                **extra,
            },
        )
        return ticket

    def registrar_pago(self, metodo, cobrado_por):
        """El personal cobra el excedente pendiente del ticket."""
        with transaction.atomic():
            resta = self.monto_a_cobrar or 0
            if resta > 0:
                Pago.objects.create(
                    movimiento=self.movimiento, ticket=self, monto=resta, metodo=metodo,
                    origen=Pago.Origen.SALIDA, registrado_por=cobrado_por,
                )
            self.estado = self.Estado.PAGADO
            self.metodo_pago = metodo
            self.fecha_pago = timezone.now()
            self.cobrado_por = cobrado_por
            self.save()
 
 
class Pago(models.Model):
    """
    Cada pago de dinero realizado: es la fuente del Dashboard de recaudación.
    Una estadía puede tener varios (una validación, otra al vencer, y el
    excedente cobrado en la salida).
    """
 
    class Origen(models.TextChoices):
        VALIDACION = "validacion", "Validación anticipada (usuario)"
        SALIDA = "salida", "Cobro en la salida (personal)"
 
    movimiento = models.ForeignKey(Movimiento, on_delete=models.PROTECT, related_name="pagos")
    ticket = models.ForeignKey(
        Ticket, on_delete=models.SET_NULL, null=True, blank=True, related_name="pagos"
    )
    monto = models.FloatField()
    metodo = models.CharField(max_length=20, choices=Ticket.Metodo.choices)
    origen = models.CharField(max_length=20, choices=Origen.choices)
    fecha_pago = models.DateTimeField(default=timezone.now)
    registrado_por = models.ForeignKey(
        Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name="pagos_registrados"
    )
 
    class Meta:
        verbose_name = "Pago"
        verbose_name_plural = "Pagos"
        ordering = ["-fecha_pago"]
 
    def __str__(self):
        return f"Pago #{self.pk} - Gs. {self.monto} ({self.get_metodo_display()})"