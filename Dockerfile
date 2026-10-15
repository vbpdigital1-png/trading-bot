FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY config.yaml ./
COPY scripts ./scripts

# data/ and logs/ are mounted as volumes; .env is passed with --env-file.
VOLUME ["/app/data", "/app/logs"]
CMD ["python", "-c", "print('No entrypoint yet: the live runner arrives in Phase 5.')"]
