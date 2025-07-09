FROM registry.access.redhat.com/ubi9/python-311:latest
WORKDIR /app

USER root


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


COPY mcp.py .
COPY requirements.txt .
COPY report_assets/ report_assets/
RUN pip install --no-cache-dir -r requirements.txt
CMD ["uvicorn", "mcp:app", "--host", "0.0.0.0", "--port", "8000"]