import sys
import os
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, HTTPException, Request as FastAPIRequest
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import boto3
from urllib.parse import urlparse
import shutil
import threading
import base64
from fastapi.responses import JSONResponse
import dotenv
import json
import tempfile
from inference_script import (
    load_tflite_interpreter,
    prepare_index_content,
    run_inference,
)

dotenv.load_dotenv()

MINIO_ENDPOINT = os.getenv("AWS_S3_ENDPOINT_URL")
CALLBACK_ENDPOINT = os.getenv("CALLBACK_ENDPOINT")

class CustomHTTPException(HTTPException):
    def __init__(self, status_code: int, detail: str, error_code: int):
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code


class Response(BaseModel):
    model_url: str | None = None
    report_url: str | None = None
    view_name: str | None = None
    poi_id: str | None = None
    message: str | None = None


class InferenceRequest(BaseModel):
    data_url: str | None = None
    inference_image: str | None = None
    model_url: str | None = None
    index_url: str | None = None
    poi_name: str | None = None
    poi_id: str | None = None
    skip_geometry: bool | None = False
    gps_lat: float | None = None
    gps_lon: float | None = None
    gps_accuracy_m: float | None = None


app = FastAPI()

# origins = ["http://localhost", "http://localhost:8000", "*"]

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )


s3 = boto3.client(
    "s3",
    endpoint_url=MINIO_ENDPOINT,
    aws_access_key_id=os.getenv("MINIO_ROOT_USER"),
    aws_secret_access_key=os.getenv("MINIO_ROOT_PASSWORD"),
)

TFLITE_MODEL_PATH = str(CURRENT_DIR / "./EfficientNetLite0.tflite")

INTERPRETER = load_tflite_interpreter(TFLITE_MODEL_PATH)
INTERPRETER_LOCK = threading.Lock()

TOUR_INDEX_CACHE = {}
TOUR_INDEX_CACHE_LOCK = threading.Lock()

def download_minio_folder(prefix: str, local_dir: str, s3_client):
    """
    Downloads all objects from `bucket_name` under `prefix` to `local_dir`,
    preserving the folder hierarchy.
    """
    print(f"Downloading {prefix} to {local_dir}")
    paginator = s3_client.get_paginator(
        "list_objects_v2"
    )  # Handles pagination :contentReference[oaicite:3]{index=3}
    for page in paginator.paginate(
        Bucket=os.getenv("AWS_STORAGE_BUCKET_NAME"), Prefix=prefix
    ):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/"):
                # Skip zero-byte “folder” markers
                continue

            # Derive the local path by stripping the prefix
            rel_path = os.path.relpath(key, prefix)
            local_path = os.path.join(local_dir, rel_path)

            # Ensure the target directory exists
            os.makedirs(os.path.dirname(local_path), exist_ok=True)

            # Download the object to the local path
            s3_client.download_file(
                os.getenv("AWS_STORAGE_BUCKET_NAME"), key, local_path
            )
            print(f"Downloaded {key} → {local_path}")
    return local_dir

def read_s3_file(file_name):
    try:
        video_key = file_name
        response = s3.get_object(
            Bucket=os.getenv("AWS_STORAGE_BUCKET_NAME"), Key=video_key
        )
        # print("RESPONSE:" + str(response))
        data = response["Body"].read()
        return data, video_key
    except Exception as e:
        print(f"Error reading file from S3: {e}")
        return None


def write_s3_file(file_path, remote_path):
    try:
        s3.upload_file(
            file_path,
            os.getenv("AWS_STORAGE_BUCKET_NAME"),
            remote_path,
        )
        print(f"File {remote_path} written to S3")
    except Exception as e:
        print(f"Error writing file {file_path} to S3: {e}")

def get_cached_tour_context(index_url: str):
    if not index_url:
        raise CustomHTTPException(
            status_code=400,
            detail="Missing index_url/model_url",
            error_code=1002,
        )

    bucket = os.getenv("AWS_STORAGE_BUCKET_NAME")

    try:
        head = s3.head_object(Bucket=bucket, Key=index_url)
        etag = head.get("ETag", "").strip('"')
    except Exception as e:
        print(f"Error checking index metadata: {e}", flush=True)
        raise CustomHTTPException(
            status_code=404,
            detail="Model not found",
            error_code=1003,
        )

    cache_key = f"{index_url}:{etag}"

    with TOUR_INDEX_CACHE_LOCK:
        cached = TOUR_INDEX_CACHE.get(cache_key)
        if cached is not None:
            return cached

    try:
        response = s3.get_object(Bucket=bucket, Key=index_url)
        raw = response["Body"].read()
        waypoint_index = json.loads(raw.decode("utf-8"))
        context = prepare_index_content(waypoint_index)
    except Exception as e:
        print(f"Error loading/parsing index from S3: {e}", flush=True)
        raise CustomHTTPException(
            status_code=500,
            detail="Error loading model index",
            error_code=1007,
        )

    with TOUR_INDEX_CACHE_LOCK:
        keys_to_remove = [
            key for key in TOUR_INDEX_CACHE
            if key.startswith(f"{index_url}:")
        ]
        for key in keys_to_remove:
            TOUR_INDEX_CACHE.pop(key, None)

        TOUR_INDEX_CACHE[cache_key] = context

    return context

def decode_base64_image(data: str) -> bytes:
    if data.startswith("data:"):
        data = data.split(",")[1]
    missing_padding = len(data) % 4
    if missing_padding:
        data += "=" * (4 - missing_padding)
    return base64.b64decode(data)

@app.get("/")
async def read_root():
    return {"Hello": "World"}    

@app.post("/cache/clear")
async def clear_cache():
    with TOUR_INDEX_CACHE_LOCK:
        cleared_count = len(TOUR_INDEX_CACHE)
        TOUR_INDEX_CACHE.clear()
        
    print(f"Cleared {cleared_count} cached tour contexts")
    
    return JSONResponse(
        status_code=200,
        content = {
            "message": f"Cleared {cleared_count} cached tour contexts",
            "cleared_count": cleared_count,
        }
    )


@app.post("/inference")
async def inference(http_request: FastAPIRequest):
    try:
        content_type = http_request.headers.get("content-type", "")

        image_bytes = None

        if content_type.startswith("multipart/form-data"):
            form = await http_request.form()

            model_url = form.get("index_url") or form.get("model_url")
            poi_name = form.get("poi_name")
            poi_id = form.get("poi_id")
            skip_geometry = str(form.get("skip_geometry", "false")).lower() == "true"

            gps_lat = form.get("gps_lat")
            gps_lon = form.get("gps_lon")
            gps_accuracy_m = form.get("gps_accuracy_m")

            gps_lat = float(gps_lat) if gps_lat not in (None, "", "null") else None
            gps_lon = float(gps_lon) if gps_lon not in (None, "", "null") else None
            gps_accuracy_m = float(gps_accuracy_m) if gps_accuracy_m not in (None, "", "null") else None

            uploaded = form.get("image") or form.get("img")
            if uploaded is None:
                raise CustomHTTPException(
                    status_code=404,
                    detail="Image not found",
                    error_code=1004,
                )

            image_bytes = await uploaded.read()

        else:
            body = await http_request.json()

            model_url = body.get("index_url") or body.get("model_url")
            poi_name = body.get("poi_name")
            poi_id = body.get("poi_id")
            skip_geometry = bool(body.get("skip_geometry", False))

            gps_lat = body.get("gps_lat")
            gps_lon = body.get("gps_lon")
            gps_accuracy_m = body.get("gps_accuracy_m")

            input_image_b64 = body.get("inference_image") or body.get("img")

            if not input_image_b64:
                raise CustomHTTPException(
                    status_code=404,
                    detail="Image not found",
                    error_code=1004,
                )

            image_bytes = decode_base64_image(input_image_b64)

        print(f"Requested model: {model_url}", flush=True)

        context = get_cached_tour_context(model_url)

        data_dir = os.path.join("/data", str(poi_id or poi_name or "unknown"))
        os.makedirs(data_dir, exist_ok=True)

        image_path = os.path.join(data_dir, "input_image.jpg")

        with open(image_path, "wb") as f:
            f.write(image_bytes)

        print("IMAGE READY", flush=True)

        with INTERPRETER_LOCK:
            result = run_inference(
                image_path=image_path,
                context=context,
                interpreter=INTERPRETER,
                skip_geometry=skip_geometry,
                gps_lat=gps_lat,
                gps_lon=gps_lon,
                gps_accuracy_m=gps_accuracy_m,
            )

        shutil.rmtree(data_dir, ignore_errors=True)

        if result is None:
            result = "No matching waypoint found."

        return JSONResponse(
            status_code=200,
            content={
                "model_url": model_url,
                "report_url": f"/reports/{poi_name}",
                "view_name": poi_name,
                "poi_id": poi_id,
                "message": result,
            },
        )

    except CustomHTTPException as e:
        raise e
    except Exception as e:
        print(f"Unexpected error: {e}", flush=True)
        raise CustomHTTPException(
            status_code=500,
            detail=str(e),
            error_code=1001,
        )