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
    correo = forms.EmailField(label="Correo electrónico")
    telefono = forms.CharField(max_length=30, required=False, label="Teléfono")
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
                correo=self.cleaned_data["correo"],
                telefono=self.cleaned_data.get("telefono", ""),
                tipo=self.cleaned_data["tipo"],
            )
        return user
