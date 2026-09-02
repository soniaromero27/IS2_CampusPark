from django.db import models

class Usuario (models.Model):
    nombre = models.CharField(max_length=255)
    apellido = models.CharField(max_length=255)

# Create your models here.
