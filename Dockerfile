FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home demo
COPY app/ .
COPY db/migrations/ /app/migrations/
COPY tests/ /tests/
USER demo
EXPOSE 8080
CMD ["sh", "-c", "python seed.py && python migrate.py && exec gunicorn --bind 0.0.0.0:8080 --workers 2 --threads 4 --timeout 60 server:app"]
