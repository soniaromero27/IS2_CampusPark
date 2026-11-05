from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError

from universidad.models import Facultad


# Tipos de usuario que se registran SOLOS, sin aprobación. El resto queda pendiente
# hasta que un Administrador lo apruebe.
TIPOS_REGISTRO_LIBRE = ("externo",)

# Nombres de TipoUsuario que tienen permisos de "personal" del estacionamiento
# (pueden registrar ingresos y salidas de cualquier vehículo).
TIPOS_PERSONAL = ("personal de estacionamiento", "administrador")

# Nombres de TipoUsuario que deben tener una Facultad asociada.
TIPOS_CON_FACULTAD = ("docente", "estudiante", "funcionario")


class TipoUsuario(models.Model):
    """
    Tipo de usuario (Docente, Estudiante, Funcionario, Externo, ...). Cada tipo
    tiene un ROL que define qué puede hacer: el administrador puede crear
    todos los tipos que quiera, pero siempre asignándoles uno de estos 4 roles.
    """
 
    class Rol(models.TextChoices):
        ADMINISTRADOR = "administrador", "Administrador"
        PERSONAL = "personal", "Personal"
        UNIVERSITARIO = "universitario", "Ciudadano Universitario"
        EXTERNO = "externo", "Externo"
 
    nombre = models.CharField(max_length=50, unique=True)
    descripcion = models.CharField(max_length=255, blank=True)
    rol = models.CharField(max_length=20, choices=Rol.choices, default=Rol.EXTERNO)
 
    class Meta:
        verbose_name = "Tipo de usuario"
        verbose_name_plural = "Tipos de usuario"
 
    def __str__(self):
        return self.nombre
 
    @property
    def requiere_aprobacion(self):
        """Registrarse con este tipo necesita la aprobación de un Administrador (todos menos Externo)."""
        return self.rol != self.Rol.EXTERNO
 
    @classmethod
    def externo_por_defecto(cls, crear=False):
        """
        El tipo Externo al que pasan los usuarios de un tipo eliminado, y el que se
        usa para cobrar a las patentes no registradas: el llamado 'Externo' o, si no
        existe, el primero con rol Externo. Con crear=True se crea si no hay ninguno.
        """
        qs = cls.objects.filter(rol=cls.Rol.EXTERNO)
        tipo = qs.filter(nombre__iexact="Externo").first() or qs.order_by("pk").first()
        if tipo is None and crear:
            tipo = cls.objects.create(
                nombre="Externo",
                descripcion="Usuario externo a la comunidad universitaria",
                rol=cls.Rol.EXTERNO,
            )
        return tipo
 
    def motivos_bloqueo_eliminar(self, perfil_actual=None):
        """Razones por las que NO se puede eliminar este tipo (lista vacía = se puede)."""
        motivos = []
        defecto = TipoUsuario.externo_por_defecto()
        if defecto is not None and defecto.pk == self.pk:
            motivos.append(
                "Es el tipo Externo por defecto: a él pasan los usuarios de los tipos que se eliminan."
            )
        if perfil_actual is not None and perfil_actual.tipo_id == self.pk:
            motivos.append("Es tu propio tipo de usuario: no podés eliminarlo.")
        if (
            self.rol == self.Rol.ADMINISTRADOR
            and self.usuarios.exists()
            and not Usuario.objects.filter(tipo__rol=self.Rol.ADMINISTRADOR).exclude(tipo=self).exists()
        ):
            motivos.append("Es el único tipo con Administradores: el sistema quedaría sin ninguno.")
        n = self.tarifas.count()
        if n:
            motivos.append(
                f"Tiene {n} tarifa{'s' if n != 1 else ''} asociada{'s' if n != 1 else ''}: "
                "cambiales el tipo desde Tarifas > editar antes de eliminarlo."
            )
        n = self.solicitudes.count()
        if n:
            motivos.append(
                f"Tiene {n} solicitud{'es' if n != 1 else ''} de registro pendiente{'s' if n != 1 else ''}: "
                "aprobalas o rechazalas primero."
            )
        return motivos
 
    def advertencias_eliminar(self):
        """Efectos secundarios (no bloqueantes) de eliminar este tipo."""
        zonas = list(self.zonas_permitidas.values_list("nombre", flat=True))
        if zonas:
            return [
                "Está habilitado en las zonas: " + ", ".join(zonas) + ". Si alguna zona queda sin "
                "tipos permitidos, podrá usarla cualquier tipo de su facultad."
            ]
        return []
 

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
    fecha_nacimiento = models.DateField()
    correo = models.EmailField(unique=True)
    telefono = models.CharField(max_length=30, blank=True)
    nro_licencia = models.IntegerField(
        null=True, blank=True, help_text="Número de licencia de conducir (si aplica)."
    )
    tipo = models.ForeignKey(
        TipoUsuario, on_delete=models.PROTECT, related_name="usuarios"
    )
    facultad = models.ForeignKey(
        Facultad,
        on_delete=models.PROTECT,
        related_name="usuarios",
        null=True,
        blank=True,
        help_text="Obligatoria para Docente, Estudiante y Funcionario (ver Usuario.requiere_facultad).",
    )
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"

    def __str__(self):
        return f"{self.nombre} ({self.tipo})"


    @property
    def es_personal(self):
        """True si el rol del tipo es Personal o Administrador."""
        return self.tipo.rol in (TipoUsuario.Rol.ADMINISTRADOR, TipoUsuario.Rol.PERSONAL)
 
    @property
    def es_administrador(self):
        return self.tipo.rol == TipoUsuario.Rol.ADMINISTRADOR
 
    @property
    def requiere_facultad(self):
        """True si el rol es Ciudadano Universitario (Docente, Estudiante, Funcionario, ...)."""
        return self.tipo.rol == TipoUsuario.Rol.UNIVERSITARIO
 
    @property
    def es_externo(self):
        return self.tipo.rol == TipoUsuario.Rol.EXTERNO
 


class SolicitudRegistro(models.Model):
    """
    Pedido de registro de un usuario NO externo, pendiente de aprobación.
    Todavía no existe el User ni el perfil: se crean recién al aprobar.
    La contraseña se guarda ya cifrada (hash), nunca en texto plano.
    Al aprobar o rechazar, la solicitud se BORRA (no queda ningún dato).
    """
    username = models.CharField(max_length=150, unique=True)
    password = models.CharField(max_length=255, help_text="Hash de la contraseña elegida.")
    nombre = models.CharField(max_length=150)
    apellido = models.CharField(max_length=150)
    documento = models.CharField(max_length=20, unique=True)
    fecha_nacimiento = models.DateField()
    correo = models.EmailField(unique=True)
    telefono = models.CharField(max_length=30, blank=True)
    nro_licencia = models.IntegerField(null=True, blank=True)
    tipo = models.ForeignKey(TipoUsuario, on_delete=models.PROTECT, related_name="solicitudes")
    facultad = models.ForeignKey(
        Facultad, on_delete=models.PROTECT, related_name="solicitudes", null=True, blank=True
    )
    fecha_solicitud = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        verbose_name = "Solicitud de registro"
        verbose_name_plural = "Solicitudes de registro"
        ordering = ["fecha_solicitud"]
 
    def __str__(self):
        return f"{self.nombre} {self.apellido} ({self.tipo})"
 
    def aprobar(self):
        """
        Crea el User (con la contraseña ya cifrada) y su perfil Usuario, y
        borra la solicitud. Llamar dentro de transaction.atomic(). Si mientras
        tanto alguien tomó el usuario, documento o correo, levanta
        ValidationError y no crea nada.
        """
        from django.contrib.auth import get_user_model
 
        User = get_user_model()
        conflictos = []
        if User.objects.filter(username__iexact=self.username).exists():
            conflictos.append("el nombre de usuario ya está en uso")
        if Usuario.objects.filter(documento=self.documento).exists():
            conflictos.append("ya existe un usuario con ese documento")
        if Usuario.objects.filter(correo=self.correo).exists():
            conflictos.append("ya existe un usuario con ese correo")
        if conflictos:
            raise ValidationError("No se puede aprobar: " + "; ".join(conflictos) + ".")
 
        user = User.objects.create(username=self.username, password=self.password)
        perfil = Usuario.objects.create(
            user=user,
            nombre=self.nombre,
            apellido=self.apellido,
            documento=self.documento,
            fecha_nacimiento=self.fecha_nacimiento,
            correo=self.correo,
            telefono=self.telefono,
            nro_licencia=self.nro_licencia,
            tipo=self.tipo,
            facultad=self.facultad,
        )
        self.delete()
        return perfil
 