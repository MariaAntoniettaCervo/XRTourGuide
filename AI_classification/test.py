#!/usr/bin/env python3
import argparse
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def run_command(cmd, cwd=None, timeout=None, env=None, verbose=True):
    if verbose:
        print("\n[RUN]", " ".join(str(x) for x in cmd))

    started = time.time()
    result = subprocess.run(
        [str(x) for x in cmd],
        cwd=str(cwd) if cwd else None,
        timeout=timeout,
        env=env,
        capture_output=True,
        text=True,
    )
    elapsed = time.time() - started

    if verbose:
        print(f"[EXIT CODE] {result.returncode} | elapsed={elapsed:.2f}s")
        if result.stdout.strip():
            print("\n[STDOUT]\n" + result.stdout)
        if result.stderr.strip():
            print("\n[STDERR]\n" + result.stderr)

    return result, elapsed


def parse_prediction(stdout: str) -> Optional[str]:
    """
    Supporta entrambi gli stili:
    - 'Recognized waypoint: ...'
    - 'No matching waypoint found.'
    """
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    for line in reversed(lines):
        if "Recognized waypoint:" in line:
            return line.split("Recognized waypoint:", 1)[1].strip()
        if "No matching waypoint found." in line:
            return None
    return None


def collect_images(query_dir: Path):
    images = []
    for p in sorted(query_dir.rglob("*")):
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
            images.append(p)
    return images


def expected_from_parent(image_path: Path, query_root: Path) -> Optional[str]:
    """
    Convenzione semplice:
    query_root/
      waypoint_A/
        img1.jpg
      waypoint_B/
        img2.jpg

    expected = nome cartella parent dell'immagine
    """
    try:
        rel = image_path.relative_to(query_root)
        if len(rel.parts) >= 2:
            return rel.parts[0]
    except Exception:
        pass
    return None

def load_query_gps_map(query_gps_json: Optional[Path]) -> dict:
    if query_gps_json is None:
        return {}
    
    with open(query_gps_json, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    if not isinstance(data, dict):
        raise ValueError("query_gps_json deve essere un dizionario con waypoint come chiavi")
    
    return data

def get_query_gps_for_image(image_path: Path, query_root: Path, gps_map:dict):
    if not gps_map:
        return None, None, None
    
    candidates = []
    
    try:
        rel = image_path.relative_to(query_root)
        rel_posix = rel.as_posix()
        candidates.extend([
            rel_posix,
            str(rel),
            image_path.name,
            str(image_path)
        ])
    except Exception:
        candidates.extend([
            image_path.name,
            str(image_path)
        ])
        
    item = None
    for key in candidates:
        if key in gps_map:
            item = gps_map[key]
            break
        
    if not isinstance(item, dict):
        return None, None, None
    
    lat = item.get("lat")
    lon = item.get("lon")
    accuracy_m = item.get("accuracy_m", item.get("gps_accuracy_m"))
    
    return lat, lon, accuracy_m

def build_train_cmd(train_script: Path, input_dir: Path, output_dir: Path, tflite_model: Path, tour_id: int, skip_pytorch: bool, waypoint_gps_json: Optional[Path] = None, default_gps_radius_m: Optional[float] = None):
    cmd = [
        sys.executable,
        train_script,
        "--input-dir", input_dir,
        "--output-dir", output_dir,
        "--tflite-model", tflite_model,
        "--tour-id", str(tour_id),
    ]
    if waypoint_gps_json is not None:
        cmd.extend(["--waypoint-gps-json", waypoint_gps_json])
        
    if default_gps_radius_m is not None:
        cmd.extend(["--default-gps-radius-m", str(default_gps_radius_m)])
        
    if skip_pytorch:
        cmd.append("--skip-pytorch")
    return cmd


def build_infer_cmd(inference_script: Path, image_path: Path, mode: str, checkpoint: Optional[Path], index_json: Optional[Path], tflite_model: Optional[Path], skip_geometry: bool, gps_lat: Optional[float] = None, gps_lon: Optional[float] = None, gps_accuracy_m: Optional[float] = None):
    """
    mode:
      - pt   -> inference_script.py --image-path ... --checkpoint model.pt
      - json -> inference_script.py --image-path ... --index-json ... --tflite-model ...
    """
    if mode == "pt":
        if checkpoint is None:
            raise ValueError("checkpoint richiesto per mode=pt")
        return [
            sys.executable,
            inference_script,
            "--image-path", image_path,
            "--checkpoint", checkpoint,
        ]

    if mode == "json":
        if index_json is None or tflite_model is None:
            raise ValueError("index_json e tflite_model richiesti per mode=json")
        cmd = [
            sys.executable,
            inference_script,
            "--image-path", image_path,
            "--index-json", index_json,
            "--tflite-model", tflite_model,
        ]
        
        if skip_geometry:
            cmd.append("--skip-geometry")
            
        if gps_lat is not None and gps_lon is not None:
            cmd.extend([
                "--gps-lat", str(gps_lat),
                "--gps-lon", str(gps_lon),
            ])
            
            if gps_accuracy_m is not None:
                cmd.extend(["--gps-accuracy-m", str(gps_accuracy_m)])
            
        return cmd

    raise ValueError(f"Mode non supportata: {mode}")


def cmd_train(args):
    ai_root = Path(args.ai_root).resolve()
    train_script = ai_root / "training" / "train_script.py"

    result, _ = run_command(
        build_train_cmd(
            train_script=train_script,
            input_dir=Path(args.input_dir).resolve(),
            output_dir=Path(args.output_dir).resolve(),
            tflite_model=Path(args.tflite_model).resolve(),
            tour_id=args.tour_id,
            skip_pytorch=args.skip_pytorch,
            waypoint_gps_json = Path(args.waypoint_gps_json).resolve() if args.waypoint_gps_json else None,
            default_gps_radius_m = args.default_gps_radius_m,
        ),
        cwd=ai_root,
        timeout=args.timeout,
        verbose=not args.quiet,
    )

    if result.returncode != 0:
        sys.exit(result.returncode)

    print("\n[OK] Training completato")
    print("Artifacts attesi:")
    print(" -", Path(args.output_dir).resolve() / "training_data.json")
    if not args.skip_pytorch:
        print(" -", Path(args.output_dir).resolve() / "model.pt")
        print(" -", Path(args.output_dir).resolve() / "training_data_pytorch.json")


def cmd_infer(args):
    ai_root = Path(args.ai_root).resolve()
    inference_script = ai_root / "inference" / "inference_script.py"

    checkpoint = Path(args.checkpoint).resolve() if args.checkpoint else None
    index_json = Path(args.index_json).resolve() if args.index_json else None
    tflite_model = Path(args.tflite_model).resolve() if args.tflite_model else None

    result, elapsed = run_command(
        build_infer_cmd(
            inference_script=inference_script,
            image_path=Path(args.image_path).resolve(),
            mode=args.mode,
            checkpoint=checkpoint,
            index_json=index_json,
            tflite_model=tflite_model,
            skip_geometry=args.skip_geometry if args.skip_geometry else False,
            gps_lat = args.gps_lat,
            gps_lon = args.gps_lon,
            gps_accuracy_m = args.gps_accuracy_m,
        ),
        cwd=ai_root,
        timeout=args.timeout,
        verbose=not args.quiet,
    )

    pred = parse_prediction(result.stdout)
    print("\n[RESULT]")
    print("  image:", Path(args.image_path).resolve())
    print("  mode:", args.mode)
    print("  prediction:", pred if pred is not None else "NO_MATCH")
    print("  elapsed_sec:", round(elapsed, 3))

    if result.returncode != 0:
        sys.exit(result.returncode)


def cmd_pipeline(args):
    """
    Esegue:
    1) training
    2) inferenza su una singola immagine oppure su una cartella di query
    """
    ai_root = Path(args.ai_root).resolve()
    train_script = ai_root / "training" / "train_script.py"
    inference_script = ai_root / "inference" / "inference_script.py"

    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    tflite_model = Path(args.tflite_model).resolve()

    checkpoint = output_dir / "model.pt"
    index_json = output_dir / "training_data.json"

    train_result, _ = run_command(
        build_train_cmd(
            train_script=train_script,
            input_dir=input_dir,
            output_dir=output_dir,
            tflite_model=tflite_model,
            tour_id=args.tour_id,
            skip_pytorch=args.skip_pytorch,
            waypoint_gps_json=Path(args.waypoint_gps_json).resolve() if args.waypoint_gps_json else None,
            default_gps_radius_m=args.default_gps_radius_m,
        ),
        cwd=ai_root,
        timeout=args.train_timeout,
        verbose=not args.quiet,
    )

    if train_result.returncode != 0:
        eprint("[FAIL] Training fallito")
        sys.exit(train_result.returncode)

    print("\n[OK] Training completato, avvio inferenza...")

    if args.image_path:
        infer_result, elapsed = run_command(
            build_infer_cmd(
                inference_script=inference_script,
                image_path=Path(args.image_path).resolve(),
                mode=args.mode,
                checkpoint=checkpoint if args.mode == "pt" else None,
                index_json=index_json if args.mode == "json" else None,
                tflite_model=tflite_model if args.mode == "json" else None,
                skip_geometry=args.skip_geometry if args.skip_geometry else False,
                gps_lat=args.gps_lat,
                gps_lon=args.gps_lon,
                gps_accuracy_m=args.gps_accuracy_m,
            ),
            cwd=ai_root,
            timeout=args.infer_timeout,
            verbose=not args.quiet,
        )
        pred = parse_prediction(infer_result.stdout)
        print("\n[PIPELINE RESULT]")
        print("  prediction:", pred if pred is not None else "NO_MATCH")
        print("  elapsed_sec:", round(elapsed, 3))
        if infer_result.returncode != 0:
            sys.exit(infer_result.returncode)
        return

    if args.query_dir:
        query_dir = Path(args.query_dir).resolve()
        query_gps_map = load_query_gps_map(Path(args.query_gps).resolve() if args.query_gps else None)
        images = collect_images(query_dir)
        if not images:
            eprint(f"[FAIL] Nessuna immagine trovata in {query_dir}")
            sys.exit(2)

        rows = []
        for img_path in images:
            gps_lat, gps_lon, gps_accuracy_m = get_query_gps_for_image(img_path, query_dir, query_gps_map)
            infer_result, elapsed = run_command(
                build_infer_cmd(
                    inference_script=inference_script,
                    image_path=img_path,
                    mode=args.mode,
                    checkpoint=checkpoint if args.mode == "pt" else None,
                    index_json=index_json if args.mode == "json" else None,
                    tflite_model=tflite_model if args.mode == "json" else None,
                    skip_geometry=args.skip_geometry if args.skip_geometry else False,
                    gps_lat=gps_lat,
                    gps_lon=gps_lon,
                    gps_accuracy_m=gps_accuracy_m,
                ),
                cwd=ai_root,
                timeout=args.infer_timeout,
                verbose=False if args.quiet else True,
            )
            pred = parse_prediction(infer_result.stdout)
            expected = expected_from_parent(img_path, query_dir)
            rows.append({
                "image_path": str(img_path),
                "expected_waypoint": expected,
                "predicted_waypoint": pred,
                "recognized": pred is not None,
                "correct": (expected is None) or (pred == expected),
                "returncode": infer_result.returncode,
                "elapsed_sec": round(elapsed, 3),
            })

        out_csv = output_dir / "pipeline_batch_results.csv"
        out_csv.parent.mkdir(parents=True, exist_ok=True)

        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "image_path",
                    "expected_waypoint",
                    "predicted_waypoint",
                    "recognized",
                    "correct",
                    "returncode",
                    "elapsed_sec",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)

        total = len(rows)
        correct = sum(1 for r in rows if r["correct"])
        recognized = sum(1 for r in rows if r["recognized"])

        print("\n[PIPELINE BATCH SUMMARY]")
        print("  total:", total)
        print("  recognized:", recognized)
        print("  correct:", correct)
        print("  recognition_rate:", round(recognized / total, 4) if total else 0.0)
        print("  accuracy:", round(correct / total, 4) if total else 0.0)
        print("  csv:", out_csv)
        return

    eprint("[FAIL] Devi specificare --image-path oppure --query-dir")
    sys.exit(2)


def cmd_batch_eval(args):
    """
    Valuta solo l'inferenza su una cartella di query già pronta.
    Convenzione:
      query_dir/
        waypoint_A/xxx.jpg
        waypoint_B/yyy.jpg
    """
    ai_root = Path(args.ai_root).resolve()
    inference_script = ai_root / "inference" / "inference_script.py"

    query_dir = Path(args.query_dir).resolve()
    images = collect_images(query_dir)
    if not images:
        eprint(f"[FAIL] Nessuna immagine trovata in {query_dir}")
        sys.exit(2)

    checkpoint = Path(args.checkpoint).resolve() if args.checkpoint else None
    index_json = Path(args.index_json).resolve() if args.index_json else None
    tflite_model = Path(args.tflite_model).resolve() if args.tflite_model else None
    out_csv = Path(args.output_csv).resolve()
    query_gps_map = load_query_gps_map(Path(args.query_gps).resolve() if args.query_gps else None)

    rows = []

    for img_path in images:
        expected = expected_from_parent(img_path, query_dir)
        gps_lat, gps_lon, gps_accuracy_m = get_query_gps_for_image(img_path, query_dir, query_gps_map)

        infer_result, elapsed = run_command(
            build_infer_cmd(
                inference_script=inference_script,
                image_path=img_path,
                mode=args.mode,
                checkpoint=checkpoint,
                index_json=index_json,
                tflite_model=tflite_model,
                skip_geometry=args.skip_geometry,
                gps_lat=gps_lat,
                gps_lon=gps_lon,
                gps_accuracy_m=gps_accuracy_m,
            ),
            cwd=ai_root,
            timeout=args.timeout,
            verbose=False if args.quiet else True,
        )

        pred = parse_prediction(infer_result.stdout)

        row = {
            "image_path": str(img_path),
            "expected_waypoint": expected,
            "predicted_waypoint": pred,
            "recognized": pred is not None,
            "correct": pred == expected if expected is not None else "",
            "returncode": infer_result.returncode,
            "elapsed_sec": round(elapsed, 3),
        }
        rows.append(row)

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "image_path",
                "expected_waypoint",
                "predicted_waypoint",
                "recognized",
                "correct",
                "returncode",
                "elapsed_sec",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    total = len(rows)
    recognized = sum(1 for r in rows if r["recognized"])
    with_expected = [r for r in rows if r["expected_waypoint"]]
    correct = sum(1 for r in with_expected if r["correct"])

    print("\n[BATCH SUMMARY]")
    print("  total:", total)
    print("  recognized:", recognized)
    print("  recognition_rate:", round(recognized / total, 4) if total else 0.0)
    if with_expected:
        print("  accuracy:", round(correct / len(with_expected), 4))
    print("  csv:", out_csv)


def main():
    parser = argparse.ArgumentParser(
        description="Local tester for AI_classification/new training and inference."
    )
    parser.add_argument(
        "--ai-root",
        default=str(Path(__file__).resolve().parent),
        help="Path to AI_classification/new",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Riduce il logging dei subprocess",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # train
    p_train = subparsers.add_parser("train", help="Testa solo il training locale")
    p_train.add_argument("--input-dir", required=True, help="Dataset root (deve contenere train/)")
    p_train.add_argument("--output-dir", required=True, help="Output artifacts dir")
    p_train.add_argument("--tflite-model", required=True, help="Path .tflite")
    p_train.add_argument("--tour-id", type=int, default=3)
    p_train.add_argument("--skip-pytorch", action="store_true")
    p_train.add_argument("--timeout", type=int, default=None)
    p_train.add_argument("--waypoint-gps-json", help="JSON waypoint -> GPS per il training index")
    p_train.add_argument("--default-gps-radius-m", type=float, default=75.0, help="Raggio GPS default waypoint")
    p_train.set_defaults(func=cmd_train)

    # infer
    p_infer = subparsers.add_parser("infer", help="Testa solo l'inferenza locale")
    p_infer.add_argument("--image-path", required=True, help="Path immagine query")
    p_infer.add_argument("--mode", choices=["pt", "json"], default="json")
    p_infer.add_argument("--checkpoint", help="Path model.pt (mode=pt)")
    p_infer.add_argument("--index-json", help="Path training_data.json (mode=json)")
    p_infer.add_argument("--tflite-model", help="Path .tflite (mode=json)")
    p_infer.add_argument("--timeout", type=int, default=None)
    p_infer.add_argument("--skip-geometry", action="store_true", help="Salta fase di verifica geometrica")
    p_infer.add_argument("--gps-lat", type=float, help="Latitudine query")
    p_infer.add_argument("--gps-lon", type=float, help="Longitudine query")
    p_infer.add_argument("--gps-accuracy-m", type=float, default=30.0, help="Accuratezza GPS query in metri")
    p_infer.set_defaults(func=cmd_infer)

    # pipeline
    p_pipeline = subparsers.add_parser("pipeline", help="Esegue training e poi inferenza")
    p_pipeline.add_argument("--input-dir", required=True, help="Dataset root (deve contenere train/)")
    p_pipeline.add_argument("--output-dir", required=True, help="Output artifacts dir")
    p_pipeline.add_argument("--tflite-model", required=True, help="Path .tflite")
    p_pipeline.add_argument("--tour-id", type=int, default=3)
    p_pipeline.add_argument("--skip-pytorch", action="store_true")
    p_pipeline.add_argument("--mode", choices=["pt", "json"], default="json")
    p_pipeline.add_argument("--image-path", help="Singola immagine query")
    p_pipeline.add_argument("--query-dir", help="Cartella query per batch (sottocartelle = waypoint atteso)")
    p_pipeline.add_argument("--train-timeout", type=int, default=None)
    p_pipeline.add_argument("--infer-timeout", type=int, default=None)
    p_pipeline.add_argument("--skip-geometry", action="store_true", help="Salta fase di verifica geometrica")
    p_pipeline.add_argument("--waypoint-gps-json", help="JSON waypoint -> GPS per il training index")
    p_pipeline.add_argument("--default-gps-radius-m", type=float, default=75.0, help="Raggio GPS default waypoint")
    p_pipeline.add_argument("--gps-lat", type=float, help="Latitudine query singola")
    p_pipeline.add_argument("--gps-lon", type=float, help="Longitudine query singola")
    p_pipeline.add_argument("--gps-accuracy-m", type=float, default=30.0, help="Accuratezza GPS query singola")
    p_pipeline.add_argument("--query-gps-json", help="JSON path relativo query image -> GPS per batch query-dir")
    p_pipeline.set_defaults(func=cmd_pipeline)

    # batch-eval
    p_eval = subparsers.add_parser("batch-eval", help="Valuta solo l'inferenza su una cartella query")
    p_eval.add_argument("--query-dir", required=True, help="Cartella query, sottocartelle = waypoint atteso")
    p_eval.add_argument("--mode", choices=["pt", "json"], default="json")
    p_eval.add_argument("--checkpoint", help="Path model.pt (mode=pt)")
    p_eval.add_argument("--index-json", help="Path training_data.json (mode=json)")
    p_eval.add_argument("--tflite-model", help="Path .tflite (mode=json)")
    p_eval.add_argument("--output-csv", default="batch_eval_results.csv", help="CSV di output")
    p_eval.add_argument("--timeout", type=int, default=None)
    p_eval.add_argument("--skip-geometry", action="store_true", help="Salta fase di verifica geometrica")
    p_eval.add_argument("--query-gps-json", help="JSON path relativo query image -> GPS per batch eval")
    p_eval.set_defaults(func=cmd_batch_eval)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()