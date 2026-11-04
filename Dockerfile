FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Gather static files (admin CSS/JS) for WhiteNoise to serve.
RUN DJANGO_SECRET_KEY=build-only python manage.py collectstatic --noinput

RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py load_stations && python manage.py ensure_superuser && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --preload"]
