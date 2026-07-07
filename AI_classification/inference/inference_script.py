import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import os
import cv2
import json
import argparse
import numpy as np
from collections import defaultdict
from PIL import Image
from tensorflow import lite as tflite
import math

from common.preprocessing import (
    preprocess_image_dart_compatible,
    build_query_views_pil,
    build_orb_input_from_bgr,
    decode_descriptors_from_base64,
    cosine_similarity_np,
    get_query_view_weights
)

# --- Configurazione e Iperparametri ---
# Soglia minima per considerare un waypoint
SIMILARITY_THRESHOLD = 0.58

# Direct accept
DIRECT_ACCEPT_THRESHOLD = 0.76
DIRECT_ACCEPT_MARGIN = 0.10
DIRECT_ACCEPT_MIN_VOTE_RATIO = 0.60

# Soft accept
SOFT_ACCEPT_THRESHOLD = 0.64
SOFT_ACCEPT_MARGIN = 0.055
SOFT_ACCEPT_MIN_VOTE_RATIO = 0.40

ORIGINAL_MIN_FOR_DIRECT = 0.56
ORIGINAL_MIN_FOR_SOFT = 0.50
AMBIGUOUS_MARGIN = 0.045

RATIO_TEST_THRESHOLD = 0.75
TOP_MATCHES_FOR_RANSAC = 120
GEOMETRY_TOP_REFS = 5
GEOMETRY_STRONG_INLIERS = 14
GEOMETRY_STRONG_RATIO = 0.12
GEOMETRY_RESCUE_MIN_SCORE = 0.56
GEOMETRY_RESCUE_MIN_MARGIN = 0.015

TOP_WAYPOINTS_TO_VERIFY = 5
TOP_ITEMS_FOR_WAYPOINT_SCORE = 3
MULTI_VIEW_ENABLED = False #TODO: valutare effettiva efficacia

GPS_PRIOR_WEIGHT = 0.20 #Quanto puo' aggiungere o rimuovere il GPS dal punteggio finale
GPS_DEFAULT_RADIUS_M = 75.0 #Raggio di confidenza predefinito per i punti GPS degli item (considerando anche possibili errori o spostamenti)
GPS_DEFAULT_ACCURACY_M = 30.0
GPS_MIN_CONFIDENCE = 0.25
GPS_FAR_MULTIPLIER = 4.0 #Distanza a cui considerare un punto GPS come "lontano" (e quindi con affinity 0) in base al raggio di confidenza. Es: 4x il raggio -> entro 4x il raggio -> affinity > 0 | oltre 4x il raggio -> affinity = 0
GPS_MIN_FAR_DISTANCE_M = 250.0 #Distanza minima a cui considerare un punto GPS come "lontano" indipendentemente dal raggio di confidenza (utile per evitare che punti con raggio molto piccolo abbiano affinity > 0 anche a distanze elevate)


def load_tflite_interpreter(tflite_path: Path):
    interpreter = tflite.Interpreter(model_path=str(tflite_path))
    interpreter.allocate_tensors()
    return interpreter


def run_tflite_embedder(interpreter, image_array: np.ndarray) -> np.ndarray:
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


def extract_query_embeddings_multi_view_tflite(image_path, interpreter):
    image = Image.open(image_path).convert("RGB")
    views = build_query_views_pil(image)

    embeddings = {}
    for view_name, pil_img in views.items():
        processed = preprocess_image_dart_compatible(pil_img)
        emb = run_tflite_embedder(interpreter, processed)
        embeddings[view_name] = emb

    return embeddings

def aggregate_waypoint_scores(best_by_source, view_names, top_k_per_waypoint=3, view_weights=None):
    view_weights = view_weights or {}
    by_waypoint = defaultdict(list)

    for (waypoint_name, _src), source_state in best_by_source.items():
        by_waypoint[waypoint_name].append(source_state)

    waypoint_stats = {}
    for waypoint_name, source_states in by_waypoint.items():
        source_states.sort(key=lambda s: s["best_score"], reverse=True)
        top_sources = source_states[:top_k_per_waypoint]

        max_score = top_sources[0]["best_score"]
        mean_score = sum(s["best_score"] for s in top_sources) / len(top_sources)

        per_view_best_scores = {}
        for view_name in view_names:
            per_view_best_scores[view_name] = max(
                s["per_view_scores"].get(view_name, -1.0)
                for s in top_sources
            )

        waypoint_stats[waypoint_name] = {
            "waypoint_name": waypoint_name,
            "max_score": max_score,
            "mean_score": mean_score,
            "per_view_best_scores": per_view_best_scores,
            "items": [s["best_item"] for s in top_sources],
        }

    view_winners = {}
    for view_name in view_names:
        best_waypoint = None
        best_score = -1.0
        for waypoint_name, stats in waypoint_stats.items():
            score = stats["per_view_best_scores"][view_name]
            if score > best_score:
                best_score = score
                best_waypoint = waypoint_name
        view_winners[view_name] = best_waypoint

    ranked = []
    total_view_weight = sum(view_weights.get(v, 1.0) for v in view_names) or 1.0

    for waypoint_name, stats in waypoint_stats.items():
        view_vote_count = sum(
            1 for winner in view_winners.values()
            if winner == waypoint_name
        )
        view_vote_weight = sum(
            view_weights.get(view_name, 1.0)
            for view_name, winner in view_winners.items()
            if winner == waypoint_name
        )
        view_vote_ratio = view_vote_weight / total_view_weight

        consensus_score = (
            0.55 * stats["max_score"] +
            0.25 * stats["mean_score"] +
            0.20 * view_vote_ratio
        )

        ranked.append({
            "waypoint_name": waypoint_name,
            "consensus_score": consensus_score,
            "max_score": stats["max_score"],
            "mean_score": stats["mean_score"],
            "view_vote_count": view_vote_count,
            "view_vote_ratio": view_vote_ratio,
            "items": stats["items"],
        })

    ranked.sort(key=lambda x: x["consensus_score"], reverse=True)
    return ranked

def l2_normalize_np(vec):
    vec = np.asarray(vec, dtype=np.float32)
    norm = np.linalg.norm(vec)
    if norm < 1e-8:
        return vec
    return vec / norm

def compute_waypoint_centroids(index):
    by_waypoint = defaultdict(list)
    seen = set()
    
    for item in index:
        waypoint_name = item['waypoint_name']
        source_image_path = item.get('source_image_path', item['image_path'])
        variant_name = item.get('variant_name', 'original')
        
        if variant_name != 'original':
            continue
        
        key = (waypoint_name, source_image_path)
        if key in seen:
            continue
        
        seen.add(key)
        
        emb = np.asarray(item['embedding'], dtype=np.float32)
        by_waypoint[waypoint_name].append(emb)
        
    centroids = {}
    for waypoint_name, embeddings in by_waypoint.items():
        centroid = np.mean(np.stack(embeddings, axis=0), axis=0)
        centroids[waypoint_name] = l2_normalize_np(centroid)
        
    return centroids

def get_geometry_reference_items(waypoint_name, ranked_items, full_index, limit=5):
    seen_sources = set()
    refs = []

    for item in ranked_items:
        src = item.get("source_image_path", item["image_path"])
        if src in seen_sources:
            continue
        seen_sources.add(src)

        for ref in full_index:
            if (
                ref["waypoint_name"] == waypoint_name
                and ref.get("source_image_path", ref["image_path"]) == src
                and ref.get("variant_name", "original") == "original"
                and ref.get("use_for_geometry", True)
            ):
                refs.append(ref)
                break

        if len(refs) >= limit:
            break

    return refs

def verify_match_geometric(query_path, candidate_item):
    try:
        img1 = cv2.imread(query_path, cv2.IMREAD_COLOR)
        if img1 is None:
            return False, 0, 0.0

        des2 = decode_descriptors_from_base64(
            candidate_item.get("descriptors_b64", ""),
            int(candidate_item.get("desc_rows", 0)),
            int(candidate_item.get("desc_cols", 0)),
        )
        if des2 is None:
            return False, 0, 0.0

        orb_query = build_orb_input_from_bgr(
            img1,
            use_clahe=True,
            use_edges=False,
            canny_low=80,
            canny_high=160,
            edge_alpha=0.25,
        )

        kp2 = [
            cv2.KeyPoint(
                x=float(p[0][0]),
                y=float(p[0][1]),
                size=31,
                angle=0,
                response=0,
                octave=0,
                class_id=0,
            )
            for p in candidate_item["keypoints"]
        ]

        orb = cv2.ORB_create(nfeatures=5000, fastThreshold=10)
        kp1, des1 = orb.detectAndCompute(orb_query, None)

        if des1 is None or len(des1) < 2 or len(des2) < 2:
            return False, 0, 0.0

        bf = cv2.BFMatcher(cv2.NORM_HAMMING)
        matches = bf.knnMatch(des1, des2, k=2)

        good_matches = []
        for pair in matches:
            if len(pair) < 2:
                continue
            m, n = pair
            if m.distance < RATIO_TEST_THRESHOLD * n.distance:
                good_matches.append(m)

        if len(good_matches) < 4:
            return False, len(good_matches), 0.0
        
        good_matches.sort(key=lambda x: x.distance)
        top_matches = good_matches[:TOP_MATCHES_FOR_RANSAC]
        
        if len(top_matches) < 4:
            return False, len(top_matches), 0.0

        src_pts = np.float32([kp1[m.queryIdx].pt for m in top_matches]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp2[m.trainIdx].pt for m in top_matches]).reshape(-1, 1, 2)

        M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        if M is None or mask is None:
            return False, 0, 0.0

        inlier_count = int(np.sum(mask))
        inlier_ratio = inlier_count / max(len(top_matches), 1)
        
        passed = (
            (inlier_count >= 8 and inlier_ratio >= 0.08)
            or
            (inlier_count >= 15)
            or
            (inlier_count >= 10 and inlier_ratio >= 0.05)
        )
        return passed, inlier_count, inlier_ratio

    except Exception as e:
        print(f"Errore durante la verifica geometrica: {e}")
        return False, 0, 0.0


def rank_waypoints_by_similarity(
    query_embeddings,
    index,
    top_k_per_waypoint=3,
    centroids=None,
    view_weights=None,
):
    view_names = list(query_embeddings.keys())
    view_weights = view_weights or {}

    best_by_source_all = {}
    best_by_source_original = {}

    for item in index:
        waypoint_name = item["waypoint_name"]
        source_image_path = item.get("source_image_path", item["image_path"])
        source_key = (waypoint_name, source_image_path)

        item_emb = np.asarray(item["embedding"], dtype=np.float32)
        variant_weight = float(item.get("variant_weight", 1.0))
        variant_name = item.get("variant_name", "original")

        per_view_scores = {}
        best_score = -1.0

        for view_name, q_emb in query_embeddings.items():
            raw_score = cosine_similarity_np(q_emb, item_emb)
            weighted_score = (
                raw_score *
                variant_weight *
                float(view_weights.get(view_name, 1.0))
            )
            per_view_scores[view_name] = weighted_score
            best_score = max(best_score, weighted_score)

        current = best_by_source_all.get(source_key)
        if current is None:
            best_by_source_all[source_key] = {
                "best_score": best_score,
                "best_item": item,
                "per_view_scores": per_view_scores,
            }
        else:
            for view_name, score in per_view_scores.items():
                current["per_view_scores"][view_name] = max(
                    current["per_view_scores"].get(view_name, -1.0),
                    score,
                )
            if best_score > current["best_score"]:
                current["best_score"] = best_score
                current["best_item"] = item

        if variant_name == "original":
            current_orig = best_by_source_original.get(source_key)
            if current_orig is None:
                best_by_source_original[source_key] = {
                    "best_score": best_score,
                    "best_item": item,
                    "per_view_scores": per_view_scores,
                }
            else:
                for view_name, score in per_view_scores.items():
                    current_orig["per_view_scores"][view_name] = max(
                        current_orig["per_view_scores"].get(view_name, -1.0),
                        score,
                    )
                if best_score > current_orig["best_score"]:
                    current_orig["best_score"] = best_score
                    current_orig["best_item"] = item

    ranked_all = aggregate_waypoint_scores(
        best_by_source_all,
        view_names,
        top_k_per_waypoint=top_k_per_waypoint,
        view_weights=view_weights,
    )

    ranked_original = aggregate_waypoint_scores(
        best_by_source_original,
        view_names,
        top_k_per_waypoint=top_k_per_waypoint,
        view_weights=view_weights,
    )

    original_by_name = {r["waypoint_name"]: r for r in ranked_original}
    centroids = centroids or {}

    final_ranked = []
    for item in ranked_all:
        waypoint_name = item["waypoint_name"]
        original_stats = original_by_name.get(waypoint_name, {
            "consensus_score": 0.0,
            "max_score": 0.0,
            "mean_score": 0.0,
            "view_vote_count": 0,
            "view_vote_ratio": 0.0,
        })

        centroid_score = 0.0
        centroid = centroids.get(waypoint_name)
        if centroid is not None:
            centroid_score = max(
                cosine_similarity_np(q_emb, centroid) * float(view_weights.get(view_name, 1.0))
                for view_name, q_emb in query_embeddings.items()
            )

        final_score = (
            0.55 * original_stats["consensus_score"] +
            0.30 * item["consensus_score"] +
            0.15 * centroid_score
        )

        final_ranked.append({
            "waypoint_name": waypoint_name,
            "consensus_score": item["consensus_score"],
            "original_consensus_score": original_stats["consensus_score"],
            "centroid_score": centroid_score,
            "final_score": final_score,
            "max_score": item["max_score"],
            "mean_score": item["mean_score"],
            "view_vote_count": item["view_vote_count"],
            "view_vote_ratio": item["view_vote_ratio"],
            "original_view_vote_ratio": original_stats["view_vote_ratio"],
            "items": item["items"],
        })

    final_ranked.sort(key=lambda x: x["final_score"], reverse=True)
    return final_ranked

def clamp(value, lo, hi):
    return max(lo, min(hi, value))


def percentile_safe(values, q, default):
    if not values:
        return default
    return float(np.percentile(np.asarray(values, dtype=np.float32), q))


def calibrate_index_from_originals(index):
    originals = []
    seen = set()

    for item in index:
        if item.get("variant_name", "original") != "original":
            continue

        waypoint_name = item["waypoint_name"]
        source = item.get("source_image_path", item["image_path"])
        key = (waypoint_name, source)
        if key in seen:
            continue
        seen.add(key)

        originals.append({
            "waypoint_name": waypoint_name,
            "embedding": l2_normalize_np(np.asarray(item["embedding"], dtype=np.float32)),
        })

    positive_scores = []
    negative_scores = []

    for i in range(len(originals)):
        for j in range(i + 1, len(originals)):
            s = cosine_similarity_np(originals[i]["embedding"], originals[j]["embedding"])
            if originals[i]["waypoint_name"] == originals[j]["waypoint_name"]:
                positive_scores.append(s)
            else:
                negative_scores.append(s)

    neg_p90 = percentile_safe(negative_scores, 90, 0.54)
    neg_p95 = percentile_safe(negative_scores, 95, 0.58)
    neg_p99 = percentile_safe(negative_scores, 99, 0.64)

    return {
        "negative_p90": neg_p90,
        "negative_p95": neg_p95,
        "negative_p99": neg_p99,
        "min_similarity_threshold": clamp(max(SIMILARITY_THRESHOLD, neg_p90 + 0.025), 0.56, 0.66),
        "soft_accept_threshold": clamp(max(SOFT_ACCEPT_THRESHOLD, neg_p95 + 0.035), 0.62, 0.74),
        "direct_accept_threshold": clamp(max(DIRECT_ACCEPT_THRESHOLD, neg_p99 + 0.035), 0.74, 0.84),
    }


def assess_image_quality(image_path):
    img = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if img is None:
        return {
            "blur_var": 0.0,
            "brightness": 0.0,
            "contrast": 0.0,
            "threshold_bump": 0.04,
            "flags": ["unreadable"],
        }

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(np.mean(gray))
    contrast = float(np.std(gray))

    bump = 0.0
    flags = []

    if blur_var < 35:
        bump += 0.035
        flags.append("very_blurry")
    elif blur_var < 70:
        bump += 0.018
        flags.append("slightly_blurry")

    if brightness < 35 or brightness > 220:
        bump += 0.025
        flags.append("bad_exposure")
    elif brightness < 50 or brightness > 205:
        bump += 0.012
        flags.append("weak_exposure")

    if contrast < 18:
        bump += 0.02
        flags.append("low_contrast")
    elif contrast < 28:
        bump += 0.01
        flags.append("weak_contrast")

    return {
        "blur_var": blur_var,
        "brightness": brightness,
        "contrast": contrast,
        "threshold_bump": min(bump, 0.06),
        "flags": flags,
    }


def verify_candidate_geometry(query_path, candidate, full_index, limit=GEOMETRY_TOP_REFS):
    refs = get_geometry_reference_items(
        candidate["waypoint_name"],
        candidate.get("items", []),
        full_index,
        limit=limit,
    )

    best = {
        "passed": False,
        "strong": False,
        "inliers": 0,
        "ratio": 0.0,
        "refs_checked": len(refs),
    }

    for ref in refs:
        passed, inliers, ratio = verify_match_geometric(str(query_path), ref)
        if inliers > best["inliers"] or (inliers == best["inliers"] and ratio > best["ratio"]):
            best.update({
                "passed": passed,
                "inliers": inliers,
                "ratio": ratio,
            })

    best["strong"] = (
        best["inliers"] >= GEOMETRY_STRONG_INLIERS and
        best["ratio"] >= GEOMETRY_STRONG_RATIO
    )

    return best

def haversine_distance_m(lat1, lon1, lat2, lon2):
    earth_radius_m = 6371000.0
    
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = (
        math.sin(delta_phi / 2) ** 2 +
        math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius_m * c

def clamp(value, min_value, max_value):
    return max(min_value, min(max_value, value))

def candidate_gps(candidate):
    for item in candidate.get("items", []):
        lat = item.get("gps_lat")
        lon = item.get("gps_lon")
        
        if lat is None or lon is None:
            continue
        
        try:
            return {
                "lat": float(lat),
                "lon": float(lon),
                "radius_m": float(item.get("gps_radius_m", GPS_DEFAULT_RADIUS_M)),
            }
        except Exception:
            continue
        
    return None

def gps_confidence_from_accuracy(accuracy_m):
    if accuracy_m is None:
        accuracy_m = GPS_DEFAULT_ACCURACY_M
        
    accuracy_m = max(float(accuracy_m), 1.0)
    
    #25m -> conf alta | 200+m -> conf bassa ma non zero
    confidence = 1.0 - max(0.0, accuracy_m - 25.0) / 175.0
    return clamp(confidence, GPS_MIN_CONFIDENCE, 1.0)

def gps_adjustment_for_candidate(candidate, query_lat, query_lon, query_accuracy_m):
    gps = candidate_gps(candidate)
    
    if gps is None:
        return {
            "gps_available": False,
            "gps_distance_m": None,
            "gps_adjustment": 0.0,
            "gps_affinity": None,
            "gps_radius_m": None,
        }
        
    distance_m = haversine_distance_m(
        query_lat,
        query_lon,
        gps["lat"],
        gps["lon"],
    )
    
    accuracy_m = float(query_accuracy_m or GPS_DEFAULT_ACCURACY_M)
    effective_radius_m = max(gps["radius_m"], accuracy_m, GPS_DEFAULT_RADIUS_M)
    
    far_distance_m = max(effective_radius_m * GPS_FAR_MULTIPLIER, GPS_MIN_FAR_DISTANCE_M)
    
    if distance_m <= effective_radius_m:
        affinity = 1.0
    elif distance_m >= far_distance_m:
        affinity = 0.0
    else:
        affinity = 1.0 - ((distance_m - effective_radius_m) / max(far_distance_m - effective_radius_m, 1.0))
        
    confidence = gps_confidence_from_accuracy(accuracy_m)
    
    adjustment = GPS_PRIOR_WEIGHT * confidence * ((affinity - 0.5) * 2.0)
    
    return {
        "gps_available": True,
        "gps_distance_m": distance_m,
        "gps_adjustment": adjustment,
        "gps_affinity": affinity,
        "gps_radius_m": gps["radius_m"],
    }
    
def apply_gps_prior_to_ranked(ranked_waypoints, query_lat, query_lon, query_accuracy_m):
    if query_lat is None or query_lon is None:
        for candidate in ranked_waypoints:
            candidate["visual_final_score"] = candidate["final_score"]
            candidate["gps_available"] = False
            candidate["gps_distance_m"] = None
            candidate["gps_adjustment"] = 0.0
            candidate["gps_affinity"] = None
            candidate["visual_rank"] = None
            candidate["gps_radius_m"] = None
        return ranked_waypoints
    
    adjusted = []
    
    for visual_rank, candidate in enumerate(ranked_waypoints, start=1):
        visual_score = candidate["final_score"]
        gps_info = gps_adjustment_for_candidate(
            candidate,
            float(query_lat),
            float(query_lon),
            query_accuracy_m
        )
        
        candidate = dict(candidate)
        candidate["visual_final_score"] = visual_score
        candidate["gps_available"] = gps_info["gps_available"]
        candidate["gps_distance_m"] = gps_info["gps_distance_m"]
        candidate["gps_adjustment"] = gps_info["gps_adjustment"]
        candidate["gps_affinity"] = gps_info["gps_affinity"]
        candidate["final_score"] = visual_score + gps_info["gps_adjustment"]
        candidate["visual_rank"] = visual_rank
        candidate["gps_radius_m"] = gps_info["gps_radius_m"]
        
        adjusted.append(candidate)
        
    adjusted.sort(key=lambda x: x["final_score"], reverse=True)
    return adjusted

def prepare_index_content(waypoint_index):
    return {
        "waypoint_index": waypoint_index,
        "centroids": compute_waypoint_centroids(waypoint_index),
        "calibrations": calibrate_index_from_originals(waypoint_index),
        "view_weights": get_query_view_weights(),
    }

def run_inference(
    image_path,
    context,
    interpreter,
    skip_geometry = False,
    gps_lat = None,
    gps_lon = None,
    gps_accuracy_m = GPS_DEFAULT_ACCURACY_M,
):
    waypoint_index = context["waypoint_index"]
    centroids = context["centroids"]
    calibration = context["calibrations"]
    view_weights = context["view_weights"]
    
    if MULTI_VIEW_ENABLED:
        query_embeddings = extract_query_embeddings_multi_view_tflite(
            image_path,
            interpreter,
        )
    else:
        image = Image.open(image_path).convert("RGB")
        processed = preprocess_image_dart_compatible(image)
        query_embeddings = {"center": run_tflite_embedder(interpreter, processed)}
        
    quality = assess_image_quality(image_path)
    
    ranked_waypoints = rank_waypoints_by_similarity(
        query_embeddings,
        waypoint_index,
        top_k_per_waypoint=TOP_ITEMS_FOR_WAYPOINT_SCORE,
        centroids=centroids,
        view_weights=view_weights,
    )
    
    if gps_lat is not None and gps_lon is not None:
        ranked_waypoints = apply_gps_prior_to_ranked(
            ranked_waypoints,
            query_lat = gps_lat,
            query_lon = gps_lon,
            query_accuracy_m=gps_accuracy_m,
        )
        
    if not ranked_waypoints:
        print("No matching waypoint found.")
        return None
    
    print("\nTop waypoint candidates:")
    if gps_lat is not None and gps_lon is not None:
        print(f"(GPS prior applied with query location: lat={gps_lat}, lon={gps_lon}, accuracy={gps_accuracy_m}m)")
        for candidate in ranked_waypoints[:TOP_WAYPOINTS_TO_VERIFY]:
            print(
                f"  - {candidate['waypoint_name']} | "
                f"final={candidate['final_score']:.4f} | "
                f"visual={candidate.get('visual_final_score', candidate['final_score']):.4f} | "
                f"gps_adj={candidate.get('gps_adjustment', 0.0):+.4f} | "
                f"gps_dist={candidate.get('gps_distance_m')} | "
                f"all={candidate['consensus_score']:.4f} | "
                f"orig={candidate['original_consensus_score']:.4f} | "
                f"votes={candidate['view_vote_count']}"
            )
    else:
        for candidate in ranked_waypoints[:TOP_WAYPOINTS_TO_VERIFY]:
            print(
                f"  - {candidate['waypoint_name']} | "
                f"final={candidate['final_score']:.4f} | "
                f"all={candidate['consensus_score']:.4f} | "
                f"orig={candidate['original_consensus_score']:.4f} | "
                f"votes={candidate['view_vote_count']}"
            )

    
    top1 = ranked_waypoints[0]
    top2_final = ranked_waypoints[1]["final_score"] if len(ranked_waypoints) > 1 else 0.0
    top2_orig = ranked_waypoints[1]["original_consensus_score"] if len(ranked_waypoints) > 1 else 0.0
    top2_gps_adjustment = ranked_waypoints[1].get("gps_adjustment", 0.0) if len(ranked_waypoints) > 1 else 0.0
    
    final_margin = top1["final_score"] - top2_final
    original_margin = top1["original_consensus_score"] - top2_orig
    
    vote_ratio = top1["view_vote_ratio"]
    original_vote_ratio = top1["original_view_vote_ratio"]
    
    quality_bump = float(quality["threshold_bump"])
    
    min_similarity_threshold = calibration["min_similarity_threshold"] + min(quality_bump, 0.04)
    soft_accept_threshold = calibration["soft_accept_threshold"] + quality_bump
    direct_accept_threshold = max(
        calibration["direct_accept_threshold"] + quality_bump,
        soft_accept_threshold + 0.045
    )
    
    top1_geometry = {"passed": False, "strong": False, "inliers": 0, "ratio": 0.0, "refs_checked": 0}
    top2_geometry = {"passed": False, "strong": False, "inliers": 0, "ratio": 0.0, "refs_checked": 0}

    if not skip_geometry:
        top1_geometry = verify_candidate_geometry(image_path, top1, waypoint_index)

        if len(ranked_waypoints) > 1 and (
            final_margin < 0.10 or top2_final >= soft_accept_threshold - 0.04
        ):
            top2_geometry = verify_candidate_geometry(image_path, ranked_waypoints[1], waypoint_index)
    
    print(
        f"Calibration -> neg_p90={calibration['negative_p90']:.4f} | "
        f"neg_p95={calibration['negative_p95']:.4f} | "
        f"neg_p99={calibration['negative_p99']:.4f}"
    )

    print(
        f"Quality -> blur={quality['blur_var']:.1f} | "
        f"brightness={quality['brightness']:.1f} | "
        f"contrast={quality['contrast']:.1f} | "
        f"bump={quality_bump:.3f} | "
        f"flags={quality['flags']}"
    )

    print(
        f"Geometry top1 -> passed={top1_geometry['passed']} | "
        f"strong={top1_geometry['strong']} | "
        f"inliers={top1_geometry['inliers']} | "
        f"ratio={top1_geometry['ratio']:.3f}"
    )

    print(
        f"Geometry top2 -> passed={top2_geometry['passed']} | "
        f"strong={top2_geometry['strong']} | "
        f"inliers={top2_geometry['inliers']} | "
        f"ratio={top2_geometry['ratio']:.3f}"
    )
        
    print(
        f"\nDecision stats -> "
        f"top1={top1['waypoint_name']} | "
        f"final={top1['final_score']:.4f} | "
        f"orig={top1['original_consensus_score']:.4f} | "
        f"top2_final={top2_final:.4f} | "
        f"final_margin={final_margin:.4f} | "
        f"orig_margin={original_margin:.4f} | "
        f"vote_ratio={vote_ratio:.2f} | "
        f"orig_vote_ratio={original_vote_ratio:.2f}"
    )

    variant_only_risk = (
        top1["original_consensus_score"] < ORIGINAL_MIN_FOR_SOFT and
        top1["consensus_score"] > top1["original_consensus_score"] + 0.08
    )

    ambiguous = (
        final_margin < AMBIGUOUS_MARGIN or
        original_margin < AMBIGUOUS_MARGIN
    )

    geometry_rescue_condition = (
        top1["final_score"] >= GEOMETRY_RESCUE_MIN_SCORE and
        final_margin >= GEOMETRY_RESCUE_MIN_MARGIN and
        top1_geometry["strong"] and
        not top2_geometry["strong"]
    )

    direct_condition = (
        top1["final_score"] >= direct_accept_threshold and
        final_margin >= DIRECT_ACCEPT_MARGIN and
        vote_ratio >= DIRECT_ACCEPT_MIN_VOTE_RATIO and
        top1["original_consensus_score"] >= ORIGINAL_MIN_FOR_DIRECT and
        not (
            top2_geometry["strong"] and
            not top1_geometry["passed"] and
            final_margin < 0.16
        )
    )

    soft_condition = (
        top1["final_score"] >= soft_accept_threshold and
        final_margin >= SOFT_ACCEPT_MARGIN and
        vote_ratio >= SOFT_ACCEPT_MIN_VOTE_RATIO and
        top1["original_consensus_score"] >= ORIGINAL_MIN_FOR_SOFT and
        (
            not ambiguous or
            top1_geometry["passed"] or
            original_margin >= SOFT_ACCEPT_MARGIN
        ) and
        (
            not variant_only_risk or
            top1_geometry["passed"]
        ) and
        not (
            top2_geometry["strong"] and
            not top1_geometry["passed"]
        )
    )

    gps_promoted_condition = (
        gps_lat is not None
        and gps_lon is not None
        and top1.get("gps_available", False)
        and top1.get("gps_distance_m") is not None
        and top1.get("gps_radius_m") is not None
        and top1.get("visual_rank", 999) <= 3
        and top1.get("visual_final_score", top1["final_score"]) >= 0.48
        and top1["final_score"] >= 0.66
        and final_margin >= 0.10
        and top1.get("gps_adjustment", 0.0) >= 0.12
        and (top1.get("gps_adjustment", 0.0) - top2_gps_adjustment) >= 0.12
        and top1["gps_distance_m"] <= max(
            top1["gps_radius_m"],
            gps_accuracy_m or GPS_DEFAULT_ACCURACY_M,
            GPS_DEFAULT_RADIUS_M,
        )
        and not top2_geometry.get("strong", False)
    )
    
    print(
        f"Effective thresholds -> min={min_similarity_threshold:.4f} | "
        f"soft={soft_accept_threshold:.4f} | "
        f"direct={direct_accept_threshold:.4f}"
    )

    print(
        f"Conditions -> direct={direct_condition} | "
        f"soft={soft_condition} | "
        f"gps_promoted={gps_promoted_condition} | "
        f"geometry_rescue={geometry_rescue_condition} | "
        f"ambiguous={ambiguous} | "
        f"variant_only_risk={variant_only_risk}"
    )

    if top1["final_score"] < min_similarity_threshold and not geometry_rescue_condition:
        print("No matching waypoint found")
        return None

    if direct_condition or gps_promoted_condition or soft_condition or geometry_rescue_condition:
        print(f"Recognized waypoint: {top1['waypoint_name']}")
        return top1["waypoint_name"]

    print("No matching waypoint found")
    return None

def main():
    parser = argparse.ArgumentParser(description="Classifica una query usando indice TFLite/JSON.")
    parser.add_argument("--image-path", required=True, help="Percorso immagine di query")
    parser.add_argument("--index-json", required=True, help="Percorso training_data.json")
    parser.add_argument("--tflite-model", required=True, help="Percorso modello TFLite")
    parser.add_argument(
        "--skip-geometry",
        action="store_true",
        help="Compatibilità: pipeline embedding-only.",
    )
    parser.add_argument("--gps-lat", type=float, default=None, help="Latitudine GPS della query")
    parser.add_argument("--gps-lon", type=float, default=None, help="Longitudine GPS della query")
    parser.add_argument("--gps-accuracy-m", type=float, default=GPS_DEFAULT_ACCURACY_M, help="Precisione GPS della query in metri")
    args = parser.parse_args()

    if not os.path.exists(args.index_json):
        print(f"Indice JSON non trovato: {args.index_json}")
        print("No matching waypoint found.")
        return None

    if not os.path.exists(args.tflite_model):
        print(f"Modello TFLite non trovato: {args.tflite_model}")
        print("No matching waypoint found.")
        return None

    with open(args.index_json, "r", encoding="utf-8") as f:
        waypoint_index = json.load(f)

    interpreter = load_tflite_interpreter(Path(args.tflite_model))
    context = prepare_index_content(waypoint_index)

    print(f"\n📸 Query: {args.image_path}")
    result = run_inference(
        image_path=args.image_path,
        context=context,
        interpreter=interpreter,
        skip_geometry=args.skip_geometry,
        gps_lat=args.gps_lat,
        gps_lon=args.gps_lon,
        gps_accuracy_m=args.gps_accuracy_m,
    )

    if result:
        print(f"Recognized waypoint: {result}")
    else:
        print("No matching waypoint found.")

if __name__ == "__main__":
    main()