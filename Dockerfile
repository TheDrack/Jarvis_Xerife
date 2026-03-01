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
COPY requirements/edge.txt requirements/core.txt requirements/
RUN pip install --no-cache-dir --user -r requirements/edge.txt

# Stage 2: Edge Runtime (with hardware support)
FROM python:3.11-slim as edge

# Install runtime dependencies for audio, GUI and GitHub CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
    portaudio19-dev \
    libportaudio2 \
    libasound2 \
    curl \
    ca-certificates \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update && apt-get install -y gh \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY app/ ./app/
COPY main.py .

ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
RUN mkdir -p data logs
CMD ["python", "main.py"]

# Stage 3: Cloud Runtime (headless, no hardware dependencies)
FROM python:3.11-slim as cloud

WORKDIR /app

# Install GitHub CLI and other system utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update && apt-get install -y gh \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster dependency installation
RUN pip install --no-cache-dir uv

# Copy requirements first
COPY requirements/core.txt requirements/

# Install dependencies using uv
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r requirements/core.txt

# Install LLM dependencies separately
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system google-generativeai groq tiktoken

# Copy application code
COPY app/domain/ ./app/domain/
COPY app/application/ ./app/application/
COPY app/adapters/infrastructure/ ./app/adapters/infrastructure/
COPY app/core/config.py ./app/core/config.py
COPY app/core/__init__.py ./app/core/__init__.py
COPY app/container.py ./app/container.py
COPY serve.py ./serve.py
COPY static/ ./static/

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
RUN mkdir -p data logs

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-8000}/health').read()" || exit 1

# Start the API server
CMD ["python", "serve.py"]
