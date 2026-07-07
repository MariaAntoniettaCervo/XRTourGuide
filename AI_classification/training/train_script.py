import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import os
import json
import base64
import argparse
import sys
import traceback
import numpy as np
from PIL import Image
from tqdm import tqdm
import cv2
from tensorflow import lite as tflite
from collections import defaultdict


from common.preprocessing import (
    preprocess_image_dart_compatible,
    build_orb_input_from_bgr,
    compute_orb_features_dart_compatible,
    generate_reference_variants,
    get_reference_variant_weights,
)


INPUT_SIZE = 224
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def load_tflite_interpreter(tflite_path: Path) -> tflite.Interpreter:
    interpreter = tflite.Interpreter(model_path=str(tflite_path))
    interpreter.allocate_tensors()
    input_details = interpreter.get_input_details()[0]
    output_details = interpreter.get_output_details()[0]
    print(f"TFLite input shape: {input_details['shape']}")
    print(f"TFLite output shape: {output_details['shape']}")
    return interpreter


def run_tflite_embedder(
    interpreter: tflite.Interpreter, image_array: np.ndarray
) -> np.ndarray:
    input_details = interpreter.get_input_details()[0]
    output_details = interpreter.get_output_details()[0]

    tensor = np.expand_dims(image_array, axis=0).astype(input_details["dtype"])
    interpreter.set_tensor(input_details["index"], tensor)
    interpreter.invoke()

    embedding = interpreter.get_tensor(output_details["index"]).squeeze()

    norm = np.linalg.norm(embedding)
    if norm > 1e-6:
        embedding = embedding / norm

    return embedding.astype(np.float32)

def load_waypoint_gps_metadata(metadata_path: Path | None):
    if metadata_path is None:
        return {}

    if not metadata_path.exists():
        print(f"Warning: GPS metadata file not found at {metadata_path}")
        return {}
    
    with open(metadata_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    if isinstance(data, dict) and "waypoints" in data and isinstance(data["waypoints"], list):
        normalized = {}
        for item in data["waypoints"]:
            name = item.get("name") or item.get("waypoint_name")
            if not name:
                continue
            normalized[name] = item
        return normalized
    
    if isinstance(data, dict):
        return data
    
    raise ValueError("Invalid GPS metadata format")

def get_waypoint_gps(gps_metadata, waypoint_name, default_radius_m):
    item = gps_metadata.get(waypoint_name)
    if not item:
        return None
    
    try:
        lat = float(item.get("lat"))
        lon = float(item.get("lon"))
        radius = float(item.get("radius_m", default_radius_m))
    except Exception:
        return None
    
    return {
        "gps_lat": lat,
        "gps_lon": lon,
        "gps_radius_m": radius,
        "has_gps": True,
    }
    

def compute_orb_features_from_variant_pil(pil_img: Image.Image):
    variant_np = np.array(pil_img.convert("RGB"))
    variant_bgr = cv2.cvtColor(variant_np, cv2.COLOR_RGB2BGR)

    orb_input = build_orb_input_from_bgr(
        variant_bgr,
        use_clahe=True,
        use_edges=False,
        canny_low=80,
        canny_high=160,
        edge_alpha=0.25,
    )

    orb = cv2.ORB_create(nfeatures=5000, fastThreshold=10)
    kp, desc = orb.detectAndCompute(orb_input, None)

    if desc is None or kp is None or len(kp) == 0:
        return [], np.array([]), 0, 0

    kp_coords = [[float(k.pt[0]), float(k.pt[1])] for k in kp]
    desc = desc.astype(np.uint8)
    rows, cols = desc.shape
    return kp_coords, desc, rows, cols

def create_training_index_with_tflite(
    tflite_model_path: Path,
    dataset_root: Path,
    output_json: Path,
    tour_id: int,
    waypoint_gps_json: Path | None = None,
    default_gps_radius_m: float = 75.0,
):
    print(f"\n🚀 Generating TFLite-based index for tour {tour_id}")
    interpreter = load_tflite_interpreter(tflite_model_path)
    index = []
    processed = 0
    variant_weights = get_reference_variant_weights()
    if waypoint_gps_json is not None:
        gps_metadata = load_waypoint_gps_metadata(waypoint_gps_json)

    for waypoint_dir in sorted(dataset_root.iterdir()):
        if not waypoint_dir.is_dir():
            continue

        waypoint_name = waypoint_dir.name
        print(f"\n📁 Waypoint: {waypoint_name}")
        
        if gps_metadata:
            waypoint_gps = get_waypoint_gps(
                gps_metadata, waypoint_name, default_gps_radius_m
            )

        valid_extensions = {".jpg", ".jpeg", ".png"}
        image_files = [
            p for p in sorted(waypoint_dir.iterdir())
            if p.is_file() and p.suffix.lower() in valid_extensions
        ]

        for img_path in image_files:
            try:
                pil_image = Image.open(img_path).convert("RGB")
                variants = generate_reference_variants(pil_image)

                for variant_name, variant_pil in variants.items():
                    try:
                        processed_array = preprocess_image_dart_compatible(variant_pil)
                        embedding = run_tflite_embedder(interpreter, processed_array)
                        
                        if variant_name == "original":
                            kp_coords, descriptors, rows, cols = compute_orb_features_from_variant_pil(
                                variant_pil
                            )
                            descriptors_b64 = ""
                            if rows > 0 and cols > 0 and descriptors.size > 0:
                                descriptors_b64 = base64.b64encode(
                                    descriptors.tobytes()
                                ).decode("utf-8")
                        else:
                            kp_coords, descriptors, rows, cols = [], np.array([]), 0, 0
                            descriptors_b64 = ""
                            

                        entry = {
                            "waypoint_name": waypoint_name,
                            "image_path": str(img_path.relative_to(dataset_root.parent)),
                            "source_image_path": str(img_path.relative_to(dataset_root.parent)),
                            "variant_name": variant_name,
                            "variant_weight": variant_weights.get(variant_name, 1.0),
                            "embedding": embedding.tolist(),
                            "keypoints": [[coord, 0, 0, 0, 0, 0, 0] for coord in kp_coords],
                            "desc_rows": rows,
                            "desc_cols": cols,
                            "descriptors_b64": descriptors_b64,
                            "use_for_geometry": variant_name == "original",
                        }
                        
                        if waypoint_gps:
                            entry.update(waypoint_gps)
                        else:
                            entry.update({
                                "has_gps": False,
                                "gps_lat": None,
                                "gps_lon": None,
                                "gps_radius_m": None,
                            })

                        index.append(entry)
                        processed += 1

                        print(
                            f"  ✅ {img_path.name} [{variant_name}]: "
                            f"emb {len(embedding)}, kpts {len(kp_coords)}"
                        )

                    except Exception as e:
                        print(f"  ❌ {img_path.name} [{variant_name}]: {e}")

            except Exception as e:
                print(f"  ❌ {img_path.name}: {e}")

    output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"\n✅ TFLite index saved to {output_json} ({processed} images/variants)")

def main():
    parser = argparse.ArgumentParser(
        description="Genera l'indice TFLite/ORB allineato alla pipeline mobile offline."
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Percorso della cartella radice del dataset.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Cartella in cui salvare i risultati.",
    )
    parser.add_argument(
        "--tflite-model",
        required=True,
        help="Percorso al modello TFLite usato nell'app mobile.",
    )
    parser.add_argument(
        "--tour-id",
        type=int,
        default=3,
        help="ID del tour.",
    )
    parser.add_argument(
        "--waypoint-gps-json",
        type=Path,
        default=None,
        help="Percorso al file JSON con i dati GPS dei waypoint (opzionale).",
    )
    parser.add_argument(
        "--default-gps-radius-m",
        type=float,
        default=75.0,
        help="Raggio in metri da usare se i dati GPS specifici del waypoint non sono disponibili (default: 75m).",
    )

    args = parser.parse_args()

    try:
        input_dir = Path(args.input_dir)
        output_dir = Path(args.output_dir)
        train_dir = input_dir / "train"

        tflite_json_path = output_dir / "training_data.json"

        if not input_dir.exists():
            raise FileNotFoundError(f"Cartella input non trovata: {input_dir}")
        if not train_dir.exists():
            raise FileNotFoundError(f"Cartella train non trovata: {train_dir}")

        tflite_model_path = Path(args.tflite_model)
        if not tflite_model_path.exists():
            raise FileNotFoundError(f"Modello TFLite non trovato: {tflite_model_path}")

        output_dir.mkdir(parents=True, exist_ok=True)

        print("\n=== STEP 1: build authoritative TFLite/mobile index ===")
        create_training_index_with_tflite(
            tflite_model_path=tflite_model_path,
            dataset_root=train_dir,
            output_json=tflite_json_path,
            tour_id=args.tour_id,
            waypoint_gps_json=args.waypoint_gps_json,
            default_gps_radius_m=args.default_gps_radius_m,
        )
        
        print("\nDone.")
        sys.exit(0)

    except Exception as e:
        print(f"FATAL ERROR: {e}", flush=True)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()