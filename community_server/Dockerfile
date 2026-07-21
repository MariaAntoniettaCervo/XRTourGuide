FROM python:3.12-slim

WORKDIR /workspace

ARG USER_ID=1000
ARG GROUP_ID=1000

COPY requirements.txt .


RUN apt-get update && \
    apt-get install -y default-libmysqlclient-dev build-essential netcat-openbsd && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt
    
COPY . .

COPY wait-for-it.sh .
# PROVA
RUN sed -i 's/\r$//' wait-for-it.sh
RUN chmod +x wait-for-it.sh

RUN groupadd -g ${GROUP_ID} appgroup && \
    useradd -u ${USER_ID} -g appgroup -m appuser

RUN chown -R appuser:appgroup /workspace
    
USER appuser


EXPOSE 8002

CMD ["./wait-for-it.sh", "db_cs", "3306", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002",  "--proxy-headers", "--workers", "2"]

