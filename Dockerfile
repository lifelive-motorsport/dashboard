FROM python:3.12-slim
WORKDIR /srv
# poppler-utils : « pdftotext -layout » lit les tableaux des factures de la carte carburant bien mieux que les bibliothèques Python
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt backend/
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend backend
COPY frontend frontend
WORKDIR /srv/backend
ENV PORT=8080
CMD exec uvicorn app.main:app --host 0.0.0.0 --port $PORT
