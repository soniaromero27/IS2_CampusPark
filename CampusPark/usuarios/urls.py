from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "usuarios"

urlpatterns = [
    path("registro/", views.registro_view, name="registro"),
    path("registro/pendiente/", views.registro_pendiente_view, name="registro_pendiente"),
    
    path("perfil/", views.perfil_view, name="perfil"),
    path("perfil/editar/", views.editar_perfil_view, name="perfil_editar"),
    path("perfil/password/", views.CambiarPasswordView.as_view(), name="password_cambiar"),
    
    path("login/", auth_views.LoginView.as_view(template_name="usuarios/login.html", redirect_authenticated_user=True), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="usuarios:login"), name="logout"),
    path("lista/", views.lista_usuarios_view, name="lista"),
    
    path("solicitudes/", views.lista_solicitudes_view, name="solicitudes"),
    path("solicitudes/<int:pk>/aprobar/", views.aprobar_solicitud_view, name="solicitud_aprobar"),
    path("solicitudes/<int:pk>/rechazar/", views.rechazar_solicitud_view, name="solicitud_rechazar"),
]