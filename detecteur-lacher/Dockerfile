FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends libportaudio2 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "numpy>=1.26,<3" "sounddevice>=0.4,<1"

WORKDIR /app
COPY detecteur.py .
ENV PYTHONUNBUFFERED=1
CMD ["python", "detecteur.py"]
