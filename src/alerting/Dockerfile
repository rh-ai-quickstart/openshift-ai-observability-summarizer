FROM registry.access.redhat.com/ubi9/python-311:latest

WORKDIR /app

RUN pip install requests llama-stack

COPY . .

CMD ["python3", "alert_receiver.py"]
