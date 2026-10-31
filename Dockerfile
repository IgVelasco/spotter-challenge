FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_DB_PATH=/data/db.sqlite3

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd --create-home app && mkdir /data && chown app /data
COPY --chown=app . .
USER app

EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py import_stations && gunicorn config.wsgi --bind 0.0.0.0:8000 --workers 2 --timeout 30"]
