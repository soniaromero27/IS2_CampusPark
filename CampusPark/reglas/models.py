from django.db import models

from usuarios.models import TipoUsuario


class ReglaAcceso(models.Model):
    """Entidad 'regla_acceso' del DER."""
    descripcion = models.CharField(max_length=255)
    horario = models.TimeField(
        help_text="Hora de referencia de la regla (ej. inicio de franja horaria)."
    )
    tolerancia = models.IntegerField(help_text="Tolerancia en minutos.")
    condicion = models.CharField(max_length=255, blank=True)

    tipos_usuario = models.ManyToManyField(
        TipoUsuario,
        through="TipoUsuarioRegla",
        related_name="reglas_acceso",
    )

    class Meta:
        verbose_name = "Regla de acceso"
        verbose_name_plural = "Reglas de acceso"

    def __str__(self):
        return self.descripcion


class TipoUsuarioRegla(models.Model):
    """
    Entidad 'tipo_usuario_regla' del DER: tabla intermedia N:M entre
    tipo_usuario y regla_acceso. El DER modela (id_regla, id_tipo) como
    clave primaria compuesta; Django no soporta PK compuesta de forma
    nativa, por lo que se usa un id autonumérico + unique_together, que
    genera la misma tabla y restricción de unicidad en la base de datos.
    """
    regla = models.ForeignKey(ReglaAcceso, on_delete=models.CASCADE)
    tipo = models.ForeignKey(TipoUsuario, on_delete=models.CASCADE)

    class Meta:
        verbose_name = "Regla por tipo de usuario"
        verbose_name_plural = "Reglas por tipo de usuario"
        unique_together = ("regla", "tipo")

    def __str__(self):
        return f"{self.tipo} - {self.regla}"


class Tarifa(models.Model):
    """Entidad 'tarifa' del DER."""
    descripcion = models.CharField(max_length=255)
    valor_por_hora = models.FloatField()
    vigencia = models.DateField()
    tipo = models.ForeignKey(
        TipoUsuario, on_delete=models.PROTECT, related_name="tarifas"
    )

    class Meta:
        verbose_name = "Tarifa"
        verbose_name_plural = "Tarifas"

    def __str__(self):
        return f"{self.descripcion} (Gs. {self.valor_por_hora}/h)"


class Reglamento(models.Model):
    """
    Reglamento general del estacionamiento: el texto del reglamento y
    el horario de apertura/cierre del campus. Visible para cualquier
    usuario logueado; sólo un Administrador puede crearlo o editarlo
    (ver usuarios.decorators.admin_requerido).
    """
    reglamento = models.TextField(
        help_text="Texto del reglamento (normas de uso, sanciones, etc.)."
    )
    hora_apertura = models.TimeField()
    hora_cierre = models.TimeField()

    class Meta:
        verbose_name = "Reglamento"
        verbose_name_plural = "Reglamentos"

    def __str__(self):
        return f"Reglamento ({self.hora_apertura} a {self.hora_cierre})"