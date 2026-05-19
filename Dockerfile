FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends antiword unrtf \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY main.py parser.py splitter.py database.py search.py auth.py ./
COPY routers ./routers
COPY services ./services
COPY web ./web

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

RUN mkdir -p /app/storage/uploads /app/storage/db

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
