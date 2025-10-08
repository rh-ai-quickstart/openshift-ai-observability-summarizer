FROM registry.access.redhat.com/ubi9/python-311:latest
WORKDIR /app
COPY ui/ui.py .
COPY ui/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
EXPOSE 8501
CMD ["streamlit", "run", "ui.py", "--server.port=8501", "--server.address=0.0.0.0"]