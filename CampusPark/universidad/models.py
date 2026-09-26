from django.db import models


class Facultad(models.Model):
    """
    Facultad de la universidad. Cada Zona del estacionamiento pertenece
    a una facultad, y cada Usuario de tipo Docente o Estudiante también
    (ver usuarios.models.Usuario.requiere_facultad).
    """
    nombre = models.CharField(max_length=150, unique=True)
    descripcion = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Facultad"
        verbose_name_plural = "Facultades"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre