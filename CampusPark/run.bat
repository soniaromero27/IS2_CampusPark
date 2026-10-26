@echo off

start chrome 127.0.0.1:8000/

py manage.py runserver 0.0.0.0:8000
