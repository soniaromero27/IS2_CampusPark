from django.contrib import admin

from .models import ReglaAcceso, Reglamento, Tarifa, TipoUsuarioRegla


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


@admin.register(Reglamento)
class ReglamentoAdmin(admin.ModelAdmin):
    list_display = ("id", "hora_apertura", "hora_cierre")

    def has_add_permission(self, request):
        # Sólo puede haber un reglamento: si ya existe, no se ofrece "Agregar".
        return not Reglamento.objects.exists()