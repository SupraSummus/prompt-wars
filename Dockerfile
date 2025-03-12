# Stage 1: Generate requirements.txt from Poetry
FROM python:3.13-slim as requirements-stage

WORKDIR /tmp

# Install Poetry
RUN pip install poetry-plugin-export

# Copy Poetry configuration files
COPY pyproject.toml poetry.lock* /tmp/

# Export dependencies to requirements.txt
RUN poetry export -f requirements.txt --output requirements.txt

# Stage 2: Build the actual application image
FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src/app

# Copy requirements.txt from the first stage
COPY --from=requirements-stage /tmp/requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run the application
ENTRYPOINT ["gunicorn", "llm_wars.wsgi"]
