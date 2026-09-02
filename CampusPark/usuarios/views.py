#from django.shortcuts import render
from django.http import HttpResponse
from django.template import loader
from .models import Usuario

def usuarios(request):
    misusuarios = Usuario.objects.all().values()
    template = loader.get_template('listausuarios.html')
    context = {
        'misusuarios': misusuarios,
       }
    return HttpResponse(template.render(context, request))
    

# Create your views here.
