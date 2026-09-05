from django.contrib import admin

from .models import TipoUsuario, Usuario


@admin.register(TipoUsuario)
class TipoUsuarioAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "descripcion")


@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "documento", "correo", "tipo", "fecha_registro")
    list_filter = ("tipo",)
    search_fields = ("nombre", "documento", "correo")
