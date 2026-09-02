#from django.shortcuts import render
from django.http import HttpResponse
from django.template import loader

def zonas(request):
    template = loader.get_template('listazonas.html')
    return HttpResponse(template.render())
# Create your views here.

