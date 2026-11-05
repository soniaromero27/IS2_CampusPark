from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.contrib.auth.forms import PasswordChangeForm, UserCreationForm
from django.contrib.auth.hashers import make_password

from universidad.models import Facultad

from .models import TipoUsuario, Usuario, SolicitudRegistro


class RegistroUsuarioForm(UserCreationForm):
    """
    Formulario de HU01 - Registrar usuario.
    Crea en un mismo paso el User de Django (login) y el perfil
    Usuario del dominio (nombre, documento, correo, telefono, tipo,
    fecha_nacimiento, nro_licencia, facultad). La facultad es
    obligatoria sólo para Docente y Estudiante (ver clean()).
    """

    nombre = forms.CharField(max_length=150, label="Nombre")
    apellido = forms.CharField(max_length=150, label="Apellido")
    documento = forms.CharField(max_length=20, label="Documento")
    fecha_nacimiento = forms.DateField(
        label="Fecha de nacimiento", widget=forms.DateInput(attrs={"type": "date"})
    )
    correo = forms.EmailField(label="Correo electrónico")
    telefono = forms.CharField(max_length=30, required=False, label="Teléfono")
    nro_licencia = forms.IntegerField(
        required=False, label="N° de licencia de conducir"
    )
    tipo = forms.ModelChoiceField(
        queryset=TipoUsuario.objects.all(), label="Tipo de usuario"
    )
    facultad = forms.ModelChoiceField(
        queryset=Facultad.objects.all(),
        required=False,
        empty_label="Ninguna",
        label="Facultad",
        help_text="Obligatoria para los tipos con rol Ciudadano Universitario (Docente, Estudiante, etc.).",
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Nombre de usuario"
        self.fields["username"].help_text = (
            "Obligatorio. Hasta 150 caracteres: letras, números y @ . + - _ solamente."
        )
        self.fields["password1"].label = "Contraseña"
        self.fields["password2"].label = "Confirmar contraseña"
        self.fields["password2"].help_text = "Escribí la misma contraseña para verificarla."
        self.fields["tipo"].help_text = (
            "Los usuarios Externos se registran al instante. Los demás tipos quedan "
            "pendientes hasta que un Administrador apruebe la solicitud."
        )
        
        self.error_messages = {
            **self.error_messages,
            "password_mismatch": "Las dos contraseñas no coinciden.",
        }
        

    def clean_username(self):
        username = super().clean_username()
        if SolicitudRegistro.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError(
                "Ese nombre de usuario ya fue solicitado y está pendiente de aprobación."
            )
        return username
 
    def clean_documento(self):
        documento = self.cleaned_data["documento"]
        if Usuario.objects.filter(documento=documento).exists():
            raise forms.ValidationError("Ya existe un usuario con ese documento.")
        if SolicitudRegistro.objects.filter(documento=documento).exists():
            raise forms.ValidationError("Ya hay una solicitud de registro pendiente con ese documento.")
        return documento
 
    def clean_correo(self):
        correo = self.cleaned_data["correo"]
        if Usuario.objects.filter(correo=correo).exists():
            raise forms.ValidationError("Ya existe un usuario con ese correo.")
        if SolicitudRegistro.objects.filter(correo=correo).exists():
            raise forms.ValidationError("Ya hay una solicitud de registro pendiente con ese correo.")
        return correo


    def clean(self):
        cleaned_data = super().clean()
        tipo = cleaned_data.get("tipo")
        facultad = cleaned_data.get("facultad")
        if tipo and tipo.rol == TipoUsuario.Rol.UNIVERSITARIO and not facultad:
            self.add_error("facultad", "Los Ciudadanos Universitarios deben indicar una facultad.")
        if tipo and tipo.rol == TipoUsuario.Rol.EXTERNO and facultad:
            self.add_error("facultad", "Los usuarios Externos no pueden pertenecer a una facultad.")
        return cleaned_data
    @property
    def requiere_aprobacion(self):
        return self.cleaned_data["tipo"].requiere_aprobacion
 
    def save(self, commit=True):
        if self.requiere_aprobacion:
            # No se crea ningún User ni perfil: sólo queda la solicitud, con la contraseña cifrada.
            return SolicitudRegistro.objects.create(
                username=self.cleaned_data["username"],
                password=make_password(self.cleaned_data["password1"]),
                nombre=self.cleaned_data["nombre"],
                apellido=self.cleaned_data["apellido"],
                documento=self.cleaned_data["documento"],
                fecha_nacimiento=self.cleaned_data["fecha_nacimiento"],
                correo=self.cleaned_data["correo"],
                telefono=self.cleaned_data.get("telefono", ""),
                nro_licencia=self.cleaned_data.get("nro_licencia"),
                tipo=self.cleaned_data["tipo"],
                facultad=self.cleaned_data.get("facultad"),
            )
 
        user = super().save(commit=commit)
        if commit:
            Usuario.objects.create(
                user=user,
                nombre=self.cleaned_data["nombre"],
                apellido=self.cleaned_data["apellido"],
                documento=self.cleaned_data["documento"],
                fecha_nacimiento=self.cleaned_data["fecha_nacimiento"],
                correo=self.cleaned_data["correo"],
                telefono=self.cleaned_data.get("telefono", ""),
                nro_licencia=self.cleaned_data.get("nro_licencia"),
                tipo=self.cleaned_data["tipo"],
                facultad=self.cleaned_data.get("facultad"),
            )
        return user
 
 
class UsuarioEditForm(forms.ModelForm):
    """
    Editar el propio perfil. No incluye 'tipo' (rol/permisos) a propósito
    -- si un usuario pudiera cambiarse su propio tipo, podría otorgarse
    a sí mismo acceso de Personal de Estacionamiento/Administrador.
    Tampoco incluye el username de login, que es un campo de User, no
    de Usuario, y esta vista no lo toca.

    'facultad' es editable, salvo para los usuarios Externos, a quienes
    ni siquiera se les muestra el campo. Como 'tipo' no está en este
    formulario, la validación de "obligatoria para Docente/Estudiante" se
    hace contra el tipo ya guardado en self.instance.
    """

    class Meta:
        model = Usuario
        fields = [
            "nombre",
            "apellido",
            "documento",
            "fecha_nacimiento",
            "correo",
            "telefono",
            "nro_licencia",
            "facultad",
        ]
        widgets = {
            "fecha_nacimiento": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.es_externo:
            # Un Externo nunca pertenece a una facultad: no se le muestra el campo
            # (y si alguien lo envía a mano, se ignora).
            del self.fields["facultad"]
        else:
            self.fields["facultad"].empty_label = "Ninguna"

    def clean_documento(self):
        documento = self.cleaned_data["documento"]
        if Usuario.objects.filter(documento=documento).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya existe un usuario con ese documento.")
        return documento

    def clean_correo(self):
        correo = self.cleaned_data["correo"]
        if Usuario.objects.filter(correo=correo).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya existe un usuario con ese correo.")
        return correo

    def clean(self):
        cleaned_data = super().clean()
        facultad = cleaned_data.get("facultad")   # None si el campo no se muestra (Externo)
        if self.instance.requiere_facultad and not facultad:
            self.add_error(
                "facultad",
                "Los Ciudadanos Universitarios deben indicar una facultad.",
            )
        if self.instance.es_externo and facultad:
            self.add_error(
                "facultad",
                "Los usuarios Externos no pueden pertenecer a una facultad.",
            )
        return cleaned_data
        

class CambiarPasswordForm(PasswordChangeForm):
    """Cambiar la propia contraseña: pide la actual y la nueva dos veces."""
 
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = "Contraseña actual"
        self.fields["new_password1"].label = "Nueva contraseña"
        self.fields["new_password2"].label = "Confirmar nueva contraseña"
        self.fields["new_password2"].help_text = "Escribí la misma contraseña para verificarla."
        

class TipoUsuarioForm(forms.ModelForm):
    """Crear o editar un tipo de usuario (sólo Administrador). Todo tipo lleva uno de los 4 roles."""
 
    class Meta:
        model = TipoUsuario
        fields = ["nombre", "descripcion", "rol"]
        help_texts = {
            "rol": (
                "Administrador: acceso total (zonas, facultades, tipos, solicitudes, dashboards). "
                "Personal: registra ingresos y salidas, ve usuarios, vehículos y todas las reservas. "
                "Ciudadano Universitario: pertenece a una facultad (Docente, Estudiante, Funcionario...). "
                "Externo: sin facultad, sólo zonas públicas, se registra sin aprobación."
            )
        }
 
    def __init__(self, *args, perfil_actual=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.perfil_actual = perfil_actual
 
    def clean_nombre(self):
        nombre = self.cleaned_data["nombre"].strip()
        otros = TipoUsuario.objects.filter(nombre__iexact=nombre)
        if self.instance.pk:
            otros = otros.exclude(pk=self.instance.pk)
        if otros.exists():
            raise forms.ValidationError("Ya existe un tipo de usuario con ese nombre.")
        if (
            self.instance.pk
            and self.instance.nombre.strip().lower() == "externo"
            and nombre.lower() != "externo"
        ):
            raise forms.ValidationError("El tipo Externo por defecto no se puede renombrar.")
        return nombre
 
    def clean(self):
        cleaned_data = super().clean()
        nombre = cleaned_data.get("nombre")
        rol = cleaned_data.get("rol")
        Rol = TipoUsuario.Rol
        if nombre and rol and nombre.lower() == "externo" and rol != Rol.EXTERNO:
            self.add_error("rol", "Un tipo llamado 'Externo' tiene que tener el rol Externo.")
 
        if self.instance.pk and rol:
            original = TipoUsuario.objects.get(pk=self.instance.pk)  # la instancia aún no se modificó
            if original.rol != rol:
                defecto = TipoUsuario.externo_por_defecto()
                if defecto is not None and defecto.pk == original.pk:
                    self.add_error("rol", "El tipo Externo por defecto no puede cambiar de rol.")
                if original.rol == Rol.ADMINISTRADOR:
                    if self.perfil_actual is not None and self.perfil_actual.tipo_id == original.pk:
                        self.add_error("rol", "No podés quitarte a vos mismo el rol de Administrador.")
                    elif (
                        original.usuarios.exists()
                        and not Usuario.objects.filter(tipo__rol=Rol.ADMINISTRADOR)
                        .exclude(tipo=original)
                        .exists()
                    ):
                        self.add_error(
                            "rol", "Es el único tipo con Administradores: el sistema quedaría sin ninguno."
                        )
        return cleaned_data