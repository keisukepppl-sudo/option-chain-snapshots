FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY requirements.txt requirements-cloudrun.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-cloudrun.txt

COPY . .

CMD exec gunicorn --bind :${PORT} --workers 1 --threads 1 --timeout 1800 cloud_run_app:app
