from django.contrib import admin

from .models import Facultad


@admin.register(Facultad)
class FacultadAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "descripcion")
    search_fields = ("nombre",)