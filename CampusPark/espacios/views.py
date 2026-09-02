#from django.shortcuts import render
from django.http import HttpResponse
from django.template import loader

def espacios(request):
    template = loader.get_template('muestra.html')
    return HttpResponse(template.render())
# Create your views here.
