from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import TipoUsuario, Usuario


class RegistroUsuarioForm(UserCreationForm):
    """
    Formulario de HU01 - Registrar usuario.
    Crea en un mismo paso el User de Django (login) y el perfil
    Usuario del dominio (nombre, documento, correo, telefono, tipo).
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

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username",)

    def clean_documento(self):
        documento = self.cleaned_data["documento"]
        if Usuario.objects.filter(documento=documento).exists():
            raise forms.ValidationError("Ya existe un usuario con ese documento.")
        return documento

    def clean_correo(self):
        correo = self.cleaned_data["correo"]
        if Usuario.objects.filter(correo=correo).exists():
            raise forms.ValidationError("Ya existe un usuario con ese correo.")
        return correo

    def save(self, commit=True):
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
            )
        return user


class UsuarioEditForm(forms.ModelForm):
    """
    Editar el propio perfil. No incluye 'tipo' (rol/permisos) a propósito
    -- si un usuario pudiera cambiarse su propio tipo, podría otorgarse
    a sí mismo acceso de Personal de Estacionamiento/Administrador.
    Tampoco incluye el username de login, que es un campo de User, no
    de Usuario, y esta vista no lo toca.
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
        ]
        widgets = {
            "fecha_nacimiento": forms.DateInput(attrs={"type": "date"}),
        }
 
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
 