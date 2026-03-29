FROM python:3.11-slim

WORKDIR /app

RUN pip install django psycopg2-binary anthropic django-cors-headers reportlab redis celery

COPY . .

EXPOSE 8000
