from django.db import models

from usuarios.models import Usuario


class Vehiculo(models.Model):
    """Corresponde a la entidad 'vehiculo' del DER (Sprint 1)."""
    matricula = models.CharField(max_length=15, unique=True)
    marca = models.CharField(max_length=50)
    modelo = models.CharField(max_length=50)
    color = models.CharField(max_length=30)
    usuario = models.ForeignKey(
        Usuario, on_delete=models.CASCADE, related_name="vehiculos"
    )
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Vehículo"
        verbose_name_plural = "Vehículos"

    def __str__(self):
        return f"{self.matricula} - {self.marca} {self.modelo}"
