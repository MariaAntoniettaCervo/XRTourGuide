import json
import os
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

class Settings:
    def __init__(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.project_root = os.path.dirname(base_dir)
        self.config_file = os.path.join(self.project_root, "config.json")
        self.tts_voice_file = os.path.join(self.project_root, "app", "tts", "assets", "ref_voice.wav")

        raw_endpoint = os.getenv("AWS_S3_ENDPOINT_URL") or os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
        parsed = urlparse(raw_endpoint if "//" in raw_endpoint else f"//{raw_endpoint}")
        self.minio_endpoint = parsed.netloc or raw_endpoint  # host:port, senza schema
        self.minio_secure = parsed.scheme == "https"

        self.minio_access_key = os.getenv("MINIO_ROOT_USER", os.getenv("MINIO_ACCESS_KEY", "minioadmin"))
        self.minio_secret_key = os.getenv("MINIO_ROOT_PASSWORD", os.getenv("MINIO_SECRET_KEY", "minioadmin"))
        self.minio_bucket = os.getenv("AWS_STORAGE_BUCKET_NAME", os.getenv("MINIO_BUCKET", "audio-tours"))

        # Defaults
        self.tts_engine = "coqui-xtts"
        self.llm_model_name = "llama3.1:8b"

        self.load()

    def load(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    data = json.load(f)
                    self.tts_engine = data.get("tts_engine", "coqui-xtts")
                    self.llm_model_name = data.get("llm_model_name", "llama3.1:8b")
            except Exception as e:
                print(f"Errore caricamento config.json: {e}")

    def save(self):
        data = {"tts_engine": self.tts_engine, "llm_model_name": self.llm_model_name}
        try:
            with open(self.config_file, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Errore salvataggio config.json: {e}")

global_settings = Settings()