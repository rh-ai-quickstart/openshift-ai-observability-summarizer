FROM registry.access.redhat.com/ubi9/python-312:latest

WORKDIR /app

# Copy and install Python dependencies via pip using requirements.txt
COPY mcp_server/requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r /app/requirements.txt

# Copy source code
COPY core /app/core
COPY mcp_server /app/mcp_server

ENV PYTHONPATH=/app
EXPOSE 8085

CMD ["python", "-m", "mcp_server.main"]


