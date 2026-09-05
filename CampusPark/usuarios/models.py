from django.conf import settings
from django.db import models


class TipoUsuario(models.Model):
    """
    Corresponde a la entidad 'tipo_usuario' del DER (Sprint 1).
    Ej: Docente, Estudiante, Funcionario, Externo, Administrador,
    Personal de estacionamiento.
    """
    nombre = models.CharField(max_length=50, unique=True)
    descripcion = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Tipo de usuario"
        verbose_name_plural = "Tipos de usuario"

    def __str__(self):
        return self.nombre


class Usuario(models.Model):
    """
    Perfil extendido del usuario de Django (auth.User), agregando los
    campos definidos en el DER: nombre, documento, correo, telefono
    e id_tipo (FK a TipoUsuario). Se usa OneToOne con el modelo de
    autenticación estándar de Django para reutilizar login/permisos.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="perfil"
    )
    nombre = models.CharField(max_length=150)
    apellido = models.CharField(max_length=150)
    documento = models.CharField(max_length=20, unique=True)
    correo = models.EmailField(unique=True)
    telefono = models.CharField(max_length=30, blank=True)
    tipo = models.ForeignKey(
        TipoUsuario, on_delete=models.PROTECT, related_name="usuarios"
    )
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"

    def __str__(self):
        return f"{self.nombre} ({self.tipo})"
