import os
import requests
from django.http import JsonResponse
from ..models import MinioStorage, Tour

def ensure_pmtiles_for_tour(tour_id: int):
    storage = MinioStorage()
    target_key = f"{tour_id}/tour_{tour_id}.pmtiles"

    if storage.exists(target_key):
        return {"ok": True, "key": target_key, "generated": False}

    try:
        tour = Tour.objects.get(pk=tour_id)
    except Tour.DoesNotExist:
        return {"ok": False, "error": "Tour not found"}

    waypoints = tour.waypoints.filter(is_preliminary_info=False).order_by("position", "id")
    if not waypoints.exists():
        return {"ok": False, "error": "No waypoints found for this tour"}

    lons, lats = [], []
    for wp in waypoints:
        try:
            lat_str, lon_str = wp.coordinates.split(",")
            lat, lon = float(lat_str.strip()), float(lon_str.strip())
            lats.append(lat)
            lons.append(lon)
        except Exception:
            continue

    if not lats or not lons:
        return {"ok": False, "error": "Waypoints have invalid coordinates"}

    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)
    bbox = f"{min_lon - 0.1},{min_lat - 0.1},{max_lon + 0.1},{max_lat + 0.1}"

    payload = {"tour_id": str(tour_id), "bbox": bbox}
    url = os.getenv("PMTILES_URL")
    if not url:
        return {"ok": False, "error": "PMTILES_URL not configured"}

    response = requests.post(url, headers={"Content-type": "application/json"}, json=payload, timeout=120)
    if response.status_code != 200:
        return {"ok": False, "error": "Failed to extract pmtiles"}

    if not storage.exists(target_key):
        return {"ok": False, "error": "PMTiles not found in storage after extract"}

    return {"ok": True, "key": target_key, "generated": True}