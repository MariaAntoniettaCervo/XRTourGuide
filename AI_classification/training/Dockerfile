FROM python:3.11-slim

WORKDIR /workspace

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu

RUN apt-get update && apt-get install -y --no-install-recommends build-essential libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
libgomp1 \
&& rm -rf /var/lib/apt/lists/*

COPY training/requirements.txt ./requirements.txt
RUN pip install --upgrade pip setuptools wheel && pip install -r requirements.txt

COPY . .

WORKDIR /workspace/training

EXPOSE 8090

CMD ["fastapi", "run", "main.py", "--port", "8090", "--host", "0.0.0.0"]