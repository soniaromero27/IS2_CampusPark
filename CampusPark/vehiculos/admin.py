from django.contrib import admin

from .models import Vehiculo


@admin.register(Vehiculo)
class VehiculoAdmin(admin.ModelAdmin):
    list_display = ("id", "matricula", "marca", "modelo", "color", "usuario")
    search_fields = ("matricula", "marca", "modelo")
