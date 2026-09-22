from django.db import models

from usuarios.models import Usuario
from vehiculos.models import Vehiculo


class Zona(models.Model):
    """Entidad 'zona' del DER (HU04 - Gestionar zonas de estacionamiento)."""
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Zona"
        verbose_name_plural = "Zonas"

    def __str__(self):
        return self.nombre


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
    estado_reserva = models.IntegerField(
        default=1, help_text="Código de estado (redundante con tipo_estado_reserva, tal como en el DER)."
    )
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
    patente = models.CharField(max_length=15, default="SIN CHAPA")
    vehiculo = models.ForeignKey(
        Vehiculo,
        on_delete=models.SET_NULL,
        related_name="movimientos",
        null=True,
        blank=True,
    )
    espacio = models.ForeignKey(Espacio, on_delete=models.CASCADE, related_name="movimientos")
 
    class Meta:
        verbose_name = "Movimiento"
        verbose_name_plural = "Movimientos"
 
    def __str__(self):
        return f"Movimiento #{self.id} - {self.patente}"
 
    @property
    def usuario_nombre(self):
        """Nombre del dueño si la patente está registrada, si no 'Desconocido'."""
        if self.vehiculo_id and self.vehiculo.usuario_id:
            return f"{self.vehiculo.usuario.nombre} {self.vehiculo.usuario.apellido}"
        return "Desconocido"
