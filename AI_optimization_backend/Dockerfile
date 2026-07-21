
FROM python:3.11-slim
 
WORKDIR /workspace
 
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu
 
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*
 
COPY requirements.txt ./requirements.txt
 
RUN pip install --upgrade pip setuptools wheel && \
    pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cpu && \
    pip install -r requirements.txt && \
    pip install TTS==0.22.0 --no-deps
 
COPY . .
 
RUN mkdir -p /workspace/models && \
    curl -L -o /workspace/models/it_IT-paola-medium.onnx \
      https://huggingface.co/rhasspy/piper-voices/resolve/main/it/it_IT/paola/medium/it_IT-paola-medium.onnx && \
    curl -L -o /workspace/models/it_IT-paola-medium.onnx.json \
      https://huggingface.co/rhasspy/piper-voices/resolve/main/it/it_IT/paola/medium/it_IT-paola-medium.onnx.json
 
EXPOSE 8000
 
CMD ["python", "-m", "app.main"]
 
