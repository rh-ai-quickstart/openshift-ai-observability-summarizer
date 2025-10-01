FROM registry.access.redhat.com/ubi9/python-312:latest

WORKDIR /app

USER root

# Install system dependencies for WeasyPrint (matching metrics-api approach)
RUN dnf install -y \
    fontconfig \
    harfbuzz \
    pango \
    cairo \
    libxml2 \
    libxslt \
    freetype \
    openjpeg2 \
    python3-devel \
    gcc \
    gcc-c++ \
    libffi-devel \
    dejavu-sans-fonts \
    && dnf clean all

USER 1001

# Copy and install Python dependencies via pip using requirements.txt
COPY mcp_server/requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r /app/requirements.txt

# Copy source code
COPY core /app/core
COPY common /app/common
COPY mcp_server /app/mcp_server

ENV PYTHONPATH=/app
EXPOSE 8085

CMD ["python", "-m", "mcp_server.main"]


