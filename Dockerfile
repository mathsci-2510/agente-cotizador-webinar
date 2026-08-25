FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# En AWS, CHECKPOINT_DB_PATH y QUOTES_DIR deben apuntar a un volumen persistente
# (o migrarse a un backend administrado, ver infra/DEPLOY_AWS.md).
RUN mkdir -p /app/data/quotes

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
