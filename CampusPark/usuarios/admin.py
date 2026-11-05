from django.contrib import admin

from .models import TipoUsuario, Usuario, SolicitudRegistro

@admin.register(TipoUsuario)
class TipoUsuarioAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "descripcion")


@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "documento", "correo", "tipo", "fecha_registro")
    list_filter = ("tipo",)
    search_fields = ("nombre", "documento", "correo")


@admin.register(SolicitudRegistro)
class SolicitudRegistroAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "apellido", "tipo", "fecha_solicitud")
    exclude = ("password",)