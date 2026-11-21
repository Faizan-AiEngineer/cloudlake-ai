FROM python:3.11-slim-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends openjdk-17-jre-headless && rm -rf /var/lib/apt/lists/*
COPY backend/requirements*.txt /requirements/
RUN pip install --no-cache-dir -r /requirements/requirements.txt -r /requirements/requirements-spark.txt -r /requirements/requirements-infra.txt
COPY backend backend
COPY data_engineering data_engineering
COPY sample_data sample_data
ENV CLOUDLAKE_HOME=/data SPARK_LOCAL_IP=127.0.0.1
CMD ["uvicorn","backend.app.main:app","--host","0.0.0.0","--port","8000"]
