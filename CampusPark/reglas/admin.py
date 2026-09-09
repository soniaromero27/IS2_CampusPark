from django.contrib import admin

from .models import ReglaAcceso, Tarifa, TipoUsuarioRegla


class TipoUsuarioReglaInline(admin.TabularInline):
    model = TipoUsuarioRegla
    extra = 1


@admin.register(ReglaAcceso)
class ReglaAccesoAdmin(admin.ModelAdmin):
    list_display = ("id", "descripcion", "horario", "tolerancia", "condicion")
    inlines = [TipoUsuarioReglaInline]


@admin.register(Tarifa)
class TarifaAdmin(admin.ModelAdmin):
    list_display = ("id", "descripcion", "valor_por_hora", "vigencia", "tipo")
    list_filter = ("tipo",)
