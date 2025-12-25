FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install tzdata for timezone support (required by zoneinfo)
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY src /app/src

RUN pip install --no-cache-dir -e . \
 && python -c "import agent; print('ok')"

CMD ["agente-email"]

