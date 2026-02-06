# Multi-stage build for Jarvis Voice Assistant
# Stage 1: Builder for dependencies
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /app

# Install system dependencies for audio
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    portaudio19-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
# Use edge requirements for full local deployment
COPY requirements/edge.txt requirements/core.txt requirements/
RUN pip install --no-cache-dir --user -r requirements/edge.txt

# Stage 2: Edge Runtime (with hardware support)
FROM python:3.11-slim as edge

# Install runtime dependencies for audio and GUI
RUN apt-get update && apt-get install -y --no-install-recommends \
    portaudio19-dev \
    libportaudio2 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY app/ ./app/
COPY main.py .

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

# Create necessary directories
RUN mkdir -p data logs

# Run the assistant
CMD ["python", "main.py"]

# Stage 3: Cloud Runtime (headless, no hardware dependencies)
FROM python:3.11-slim as cloud

WORKDIR /app

# Install only core dependencies (no hardware)
COPY requirements/core.txt requirements/
RUN pip install --no-cache-dir -r requirements/core.txt

# Copy application code (only domain, application, and infrastructure adapters)
COPY app/domain/ ./app/domain/
COPY app/application/ ./app/application/
COPY app/adapters/infrastructure/ ./app/adapters/infrastructure/
COPY app/core/config.py ./app/core/config.py
COPY app/core/__init__.py ./app/core/__init__.py
COPY app/container.py ./app/container.py
COPY serve.py ./serve.py

ENV PYTHONUNBUFFERED=1
RUN mkdir -p data logs

# Start the API server with Uvicorn
CMD ["python", "serve.py"]
