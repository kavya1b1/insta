FROM mcr.microsoft.com/playwright/python:v1.52.0-noble

RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

ENV PORT=10000

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT}