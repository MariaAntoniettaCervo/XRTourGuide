# XRTourGuide AI Backend

<p align="center">
  <img src="../assets/logo.png" alt="XRTourGuide AI Backend" width="200"/>
</p>

<h3 align="center">An AI-powered content optimization and audio-guide generation service for XRTourGuide</h3>

<p align="center">
  Turning rough tour descriptions into polished, narrated experiences
</p>

<p align="center">
  <a href="#-features">Features</a> •
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-documentation">Documentation</a> •
  <a href="#-extensibility">Extensibility</a> •
  <a href="#-known-limitations">Known Limitations</a> •
  <a href="#-contributing">Contributing</a> •
  <a href="#-community">Community</a>
</p>

<p align="center">
  <a href="https://github.com/isislab-unisa/XRTourGuide/blob/main/LICENSE">
    <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License">
  </a>
  <a href="https://github.com/isislab-unisa/XRTourGuide/stargazers">
    <img src="https://img.shields.io/github/stars/isislab-unisa/XRTourGuide?style=social" alt="Stars">
  </a>
  <a href="https://github.com/isislab-unisa/XRTourGuide/network/members">
    <img src="https://img.shields.io/github/forks/isislab-unisa/XRTourGuide?style=social" alt="Forks">
  </a>
  <a href="https://github.com/isislab-unisa/XRTourGuide/issues">
    <img src="https://img.shields.io/github/issues/isislab-unisa/XRTourGuide" alt="Issues">
  </a>
  <a href="https://github.com/isislab-unisa/XRTourGuide/pulls">
    <img src="https://img.shields.io/github/issues-pr/isislab-unisa/XRTourGuide" alt="Pull Requests">
  </a>
</p>

---

## 🌟 Overview

**XRTourGuide AI Backend** is a standalone FastAPI service that brings generative AI to the XRTourGuide platform. It rewrites rough tour and waypoint text into polished, audio-ready narration, corrects and formats Markdown content, and synthesizes natural-sounding audio guides — all without ever touching the main Django platform's codebase directly.

It is designed to be called by XRTourGuide (or any compatible platform) over the internal Docker network, using a simple async pattern: the caller starts a job, the service processes it in the background, and the result is delivered either synchronously (text) or via callback (audio).

### Why XRTourGuide AI Backend?

- **Storytelling, not just spell-check** — rewrites descriptions in an engaging, documentary-narrator style, tuned for text-to-speech playback
- **Two LLMs to choose from** — Llama 3.1 8B for quality, Qwen 2.5 7B for speed
- **Two TTS engines to choose from** — Piper for fast CPU synthesis, Coqui XTTS for a more natural voice
- **Context-aware** — knows the difference between a Tour's full narrative description and a Waypoint's short list preview, and adjusts length accordingly
- **Fact-checking built into the prompt** — instructed to avoid inventing dates, names, or anachronistic details
- **Deploy Anywhere** — Docker-ready, ships alongside its own Ollama container

---

## Features

### Core Capabilities

- **Title Optimization** — generates three title variants (short, evocative, question-style) plus a recommended pick
- **Description Optimization** — rewrites tour/waypoint descriptions for audio narration, with a `length_mode` that distinguishes a Tour's extended narrative from a Waypoint's brief list preview
- **Markdown Proofreading** — corrects grammar and formatting in Markdown content while preserving headings, lists, and emphasis
- **Audio Generation (TTS)** — converts final text into MP3, with automatic caching by content hash and an async callback to notify the caller when ready
- **TTS Chunk Precomputation** — splits finalized text into speech-friendly chunks ahead of time, so audio generation doesn't have to do it on the fly

### Technical Stack

- **Backend:** FastAPI (Python 3.11)
- **LLM Inference:** Ollama (Llama 3.1 8B, Qwen 2.5 7B)
- **Text-to-Speech:** Piper (CPU-friendly) and Coqui XTTS v2 (higher quality, GPU-friendly)
- **Storage:** MinIO / S3-compatible object storage
- **Containerization:** Docker & Docker Compose

---

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (20.10+)
- [Docker Compose](https://docs.docker.com/compose/install/) (1.29+)
- ~10 GB free disk space (LLM and TTS models are large)
- A running MinIO (or S3-compatible) instance reachable from the container

### Installation

1. **Clone the repository**

```bash
git clone https://github.com/isislab-unisa/XRTourGuide.git
cd XRTourGuide/ai_optimization_backend
```

2. **Configure environment variables**

Create a `.env` file (or reuse the platform's, if deploying alongside XRTourGuide):

```bash
# MinIO / S3 storage
MINIO_ROOT_USER=your_minio_user
MINIO_ROOT_PASSWORD=your_minio_password
AWS_STORAGE_BUCKET_NAME=points-of-interests
AWS_S3_ENDPOINT_URL=http://minio:9000

# Ollama (LLM inference)
OLLAMA_HOST=http://ollama:11434

# Coqui XTTS license acceptance (required for non-interactive use)
COQUI_TOS_AGREED=1
```

> ⚠️ **Coqui XTTS license:** `COQUI_TOS_AGREED=1` auto-accepts the [Coqui Public Model License (CPML)](https://coqui.ai/cpml) on first use. Without it, the first Coqui request will hang waiting for an interactive `[y/n]` prompt that a container can never answer.

3. **Launch with Docker**

```bash
docker compose up -d --build ai_backend ollama
```

4. **Pull the LLM models** (first time only)

```bash
docker exec -it <ollama_container_name> ollama pull llama3.1:8b
docker exec -it <ollama_container_name> ollama pull qwen2.5:7b
```

5. **Verify installation**

- **API Documentation (Swagger):** http://localhost:8000/docs
- **Logs:** `docker compose logs ai_backend -f` should show `Avvio Backend XRTourGuide...` followed by a successful MinIO bucket check and `Uvicorn running on http://0.0.0.0:8000`

---

## Documentation

### API Reference

Once running, explore the interactive API documentation:

- **Swagger UI:** http://localhost:8000/docs

### Main Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/optimize/title` | POST | Generate 3 title variants + a recommended pick |
| `/optimize/description` | POST | Rewrite a description for audio narration (`length_mode`: `lungo` for Tours, `breve` for Waypoints) |
| `/optimize-markdown` | POST | Proofread and clean up Markdown content |
| `/compute-chunks` | POST | Precompute TTS chunks for a finalized text |
| `/generate-audio` | POST | Generate (or fetch from cache) an MP3 for a given text; notifies a `callback_url` when ready |

All request/response schemas, examples, and field descriptions are available live in the Swagger UI.

### Project Structure

```
ai_optimization_backend/
├── app/
│   ├── main.py             # FastAPI app, route definitions
│   ├── schemas.py          # Pydantic request/response models
│   ├── app_config.py       # MinIO/storage configuration
│   ├── storage.py          # MinIO read/write helpers
│   └── llm/
│       ├── factory.py      # LLM engine selection (Llama / Qwen via Ollama)
│       └── services/       # One service per capability
│           ├── optimize_title.py
│           ├── optimize_description.py
│           └── optimize_markdown.py
├── Dockerfile
├── requirements.txt
└── README.md                # This file
```

---

## 🔧 Extensibility

The service is designed from the ground up to be **model-agnostic**: both the LLM and the TTS layers are built around a Factory pattern (`LLMFactory` / `TTSFactory`), so new models and engines can be added at any time without touching the API layer or the calling platform.

### Adding a new LLM model

Since LLM inference goes through Ollama, adding a new model is usually configuration, not code:

1. Pull the model into Ollama: `ollama pull <model-name>`
2. Add the matching value to `LLMModelEnum` in `app/schemas.py`
3. That's it — `LLMFactory` resolves any model by its Ollama tag, so no changes are needed in the optimization services themselves

### Adding a new TTS engine

Adding a brand-new synthesis engine (beyond Piper and Coqui XTTS) requires a small amount of code, but no changes to the public API:

1. Implement a new engine class exposing the same contract as the existing ones (a `generate_audio(text, output_filename, chunks)` method)
2. Register it in `TTSFactory`, mapping it to a new engine name
3. Add the matching value to `TTSModelEnum` in `app/schemas.py`

Once registered, the new engine becomes selectable exactly like Piper/Coqui — through the existing `tts_engine` field on `/generate-audio`, with no changes needed on the caller's side.


- **First request per model is slow.** Both Ollama models and the Coqui XTTS model are loaded lazily — the very first request that uses a given model will pay a one-time cold-start cost (downloading and/or loading into memory) before responding.
- **Coqui XTTS on CPU is slow.** Expect noticeably longer generation times than Piper; a GPU is recommended for production use of Coqui.
- **No built-in retry for stale error caching.** A failed generation attempt is cached as an error for the same text+engine combination; callers must explicitly pass `retry: true` to force a new attempt.
- **LLM prompt length affects response time.** Longer, more detailed prompts (needed to keep the model's output format consistent) take proportionally longer to process, especially on CPU-bound inference.

---

## Contributing

We love contributions! Whether you're fixing bugs, improving docs, or proposing new features, your help is welcome.

### How to Contribute

1. **Fork the repository**
2. **Create a feature branch**
   ```bash
   git checkout -b feature/amazing-feature
   ```
3. **Make your changes**
4. **Commit with clear messages**
   ```bash
   git commit -m "Add amazing feature"
   ```
5. **Push to your fork**
   ```bash
   git push origin feature/amazing-feature
   ```
6. **Open a Pull Request**

### Development Setup

```bash
# Clone your fork
git clone https://github.com/isislab-unisa/XRTourGuide.git

cd XRTourGuide/ai_optimization_backend/

docker compose up -d --build
```

---

## Issues & Support

### Reporting Bugs

Found a bug? Please [open an issue](https://github.com/isislab-unisa/XRTourGuide/issues/new) with:

- Clear description of the problem
- Steps to reproduce
- Expected vs actual behavior
- Your environment (OS, Docker version, GPU availability, etc.)

### Feature Requests

Have an idea? We'd love to hear it! [Create a feature request](https://github.com/isislab-unisa/XRTourGuide/issues/new) and let's discuss.

---

## Community

Join our community and connect with other contributors!

- **GitHub Discussions:** [Join the conversation](https://github.com/isislab-unisa/XRTourGuide/discussions)
- **Issue Tracker:** [Report bugs or request features](https://github.com/isislab-unisa/XRTourGuide/issues)
- **Contact:** [isislab@unisa.it](mailto:isislab@unisa.it)

---

## License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

```
MIT License

Copyright (c) 2024 ISISLab - University of Salerno

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 🙏 Acknowledgments

- Built with ❤️ by [ISISLab](https://www.isislab.it/) at the University of Salerno
- Powered by [FastAPI](https://fastapi.tiangolo.com/), [Ollama](https://ollama.com/), [Coqui TTS](https://github.com/coqui-ai/TTS), and [Piper](https://github.com/rhasspy/piper)
- Thanks to all our [contributors](https://github.com/isislab-unisa/XRTourGuide/graphs/contributors)!

---

<p align="center">
  <sub>Made with ❤️ to make every tour a story worth listening to</sub>
</p>

<p align="center">
  <a href="#xrtourguide-ai-backend">Back to Top ↑</a>
</p>