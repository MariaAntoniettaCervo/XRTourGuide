import json
import logging
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import io
from PIL import Image, ImageOps, UnidentifiedImageError

from django.core.files.base import ContentFile
from django.db.models import Prefetch
from django.utils import timezone

from ..models import (
    Category,
    MinioStorage,
    Tour,
    TypeOfImage,
    Waypoint,
    WaypointViewImage,
    WaypointViewLink,
)
from ..serializers import TourSerializer, WaypointSerializer
from .map_extract_service import ensure_pmtiles_for_tour

logger = logging.getLogger(__name__)

IMAGE_MAX_SIZE = (1600, 1600)
IMAGE_JPEG_QUALITY = 75
OPTIMIZE_IMAGES_FOR_OFFLINE = True
INCLUDE_VIDEO_IN_OFFLINE_BUNDLE = False

class OfflineBundleError(Exception):
    pass


class OfflineBundleService:
    """
    Genera un bundle offline unico per un tour:

    Struttura output ZIP (root):
      - tour_data.json
      - tour_<id>.pmtiles                (se disponibile / richiesto)
      - training_data.json               (solo se presente su storage -> AI allenata)
      - default_image.<ext>
      - waypoint_<id>/
          - image_0.jpg.zlib
          - image_1.jpg.zlib
          - ...
          - readme.md
          - links.json
          - audio.mp4 (o estensione reale)
          - video.mp4
          - pdf.pdf
      - subtour_<subtour_id>/
          - waypoint_<id>/...

    NOTE:
    - I path dentro tour_data.json sono RELATIVI al root del tour offline.
      Il client mobile può convertirli in assoluti dopo estrazione.
    """

    # dove salvare il bundle su MinIO
    BUNDLE_STORAGE_KEY_TEMPLATE = "{tour_id}/offline/offline_bundle.zip"
    MANIFEST_STORAGE_KEY_TEMPLATE = "{tour_id}/offline/offline_manifest.json"

    # formato/versione bundle
    BUNDLE_FORMAT_VERSION = "2.0"

    # estensioni già compresse -> ZIP_STORED
    STORED_EXTENSIONS = {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".gif",
        ".mp4",
        ".mkv",
        ".mov",
        ".mp3",
        ".wav",
        ".ogg",
        ".aac",
        ".pdf",
        ".pmtiles",
        ".zlib",
        ".gz",
        ".zip",
    }

    # estensioni comprimibili bene -> ZIP_DEFLATED
    DEFLATED_EXTENSIONS = {
        ".json",
        ".md",
        ".txt",
        ".csv",
        ".xml",
    }

    def __init__(self):
        self.storage = MinioStorage()

    # ------------------------- PUBLIC API -------------------------

    def build_offline_bundle(self, tour_id: int) -> Dict[str, Any]:
        """
        Genera il bundle e lo carica su MinIO.
        """
        tour = self._get_tour_for_bundle(tour_id)

        # 1) garantisce estrazione mappa PMTiles (richiesta esplicita)
        map_result = ensure_pmtiles_for_tour(tour_id)
        if not map_result.get("ok"):
            raise OfflineBundleError(f"PMTiles generation failed: {map_result.get('error')}")

        pmtiles_key = map_result["key"]

        with tempfile.TemporaryDirectory(prefix=f"offline_bundle_{tour_id}_") as temp_dir:
            temp_dir_path = Path(temp_dir)
            zip_path = temp_dir_path / f"tour_{tour_id}_offline_bundle.zip"

            bundle_manifest: Dict[str, Any] = {
                "bundle_format_version": self.BUNDLE_FORMAT_VERSION,
                "tour_id": tour_id,
                "generated_at": timezone.now().isoformat(),
                "has_ai_index": False,
                "has_pmtiles": False,
                "included_files": {},
            }

            # 2) costruzione payload tour_data compatibile mobile
            tour_data_payload = self._build_tour_data_payload(tour)

            # 3) prepara tour_data.json su disco temporaneo (poi nello zip)
            tour_data_path = temp_dir_path / "tour_data.json"
            tour_data_path.write_text(
                json.dumps(tour_data_payload, ensure_ascii=False),
                encoding="utf-8",
            )

            # 4) crea ZIP
            with zipfile.ZipFile(zip_path, mode="w", allowZip64=True) as zf:
                # tour_data.json
                # self._zip_add_file(zf, tour_data_path, "tour_data.json")
                bundle_manifest["included_files"]["tour_data"] = "tour_data.json"

                # default image tour principale
                default_image_arc = self._add_tour_default_image(zf, tour)
                if default_image_arc:
                    bundle_manifest["included_files"]["default_image"] = default_image_arc

                # pmtiles (obbligatoria se map_result ok)
                pmtiles_arc = f"tour_{tour_id}.pmtiles"
                self._zip_add_storage_key(zf, pmtiles_key, pmtiles_arc)
                bundle_manifest["has_pmtiles"] = True
                bundle_manifest["included_files"]["pmtiles"] = pmtiles_arc

                # training_data.json opzionale
                training_key = f"{tour_id}/training_data.json"
                if self.storage.exists(training_key):
                    self._zip_add_storage_key(zf, training_key, "training_data.json")
                    bundle_manifest["has_ai_index"] = True
                    bundle_manifest["included_files"]["training_data"] = "training_data.json"

                # waypoint principali
                for wp in tour.waypoints.all():
                    self._add_waypoint_to_zip(
                        zf=zf,
                        waypoint=wp,
                        waypoint_prefix=f"waypoint_{wp.id}",
                        waypoint_json_record=self._find_waypoint_record(
                            tour_data_payload["waypoints"], wp.id
                        ),
                    )

                # subtours
                sub_tours_payload = tour_data_payload.get("sub_tours") or []
                subtours_map = {st["sub_tour"]["id"]: st for st in sub_tours_payload if st.get("sub_tour")}

                for sub_tour in tour.sub_tours.all():
                    sub_prefix = f"subtour_{sub_tour.id}"

                    # default image subtour (opzionale ma utile)
                    sub_default_image_arc = self._add_tour_default_image(
                        zf,
                        sub_tour,
                        archive_prefix=sub_prefix,
                    )
                    if sub_default_image_arc:
                        bundle_manifest["included_files"].setdefault("subtour_default_images", {})[
                            str(sub_tour.id)
                        ] = sub_default_image_arc

                    sub_payload = subtours_map.get(sub_tour.id)
                    sub_waypoints_payload = (sub_payload or {}).get("waypoints", [])

                    for wp in sub_tour.waypoints.all():
                        wp_json = self._find_waypoint_record(sub_waypoints_payload, wp.id)
                        self._add_waypoint_to_zip(
                            zf=zf,
                            waypoint=wp,
                            waypoint_prefix=f"{sub_prefix}/waypoint_{wp.id}",
                            waypoint_json_record=wp_json,
                        )

                # aggiorna tour_data.json nel bundle con i path riempiti
                # (riscriviamo entry nel zip dopo aver popolato local_resources/local_images)
                updated_tour_data_bytes = json.dumps(
                    tour_data_payload,
                    ensure_ascii=False,
                ).encode("utf-8")
                zf.writestr(
                    "tour_data.json",
                    updated_tour_data_bytes,
                    compress_type=zipfile.ZIP_DEFLATED,
                    compresslevel=9,
                )

                # manifest interno del bundle
                zf.writestr(
                    "offline_bundle_manifest.json",
                    json.dumps(bundle_manifest, ensure_ascii=False, indent=2),
                    compress_type=zipfile.ZIP_DEFLATED,
                    compresslevel=9,
                )

            # 5) upload ZIP su MinIO
            bundle_storage_key = self.BUNDLE_STORAGE_KEY_TEMPLATE.format(tour_id=tour_id)
            self._upload_file_to_storage(zip_path, bundle_storage_key)

            # 6) upload manifest lato storage
            manifest_storage_key = self.MANIFEST_STORAGE_KEY_TEMPLATE.format(tour_id=tour_id)
            self.storage.save(
                manifest_storage_key,
                ContentFile(json.dumps(bundle_manifest, ensure_ascii=False, indent=2).encode("utf-8")),
            )

            bundle_size = zip_path.stat().st_size

        return {
            "ok": True,
            "tour_id": tour_id,
            "bundle_key": bundle_storage_key,
            "manifest_key": manifest_storage_key,
            "size_bytes": bundle_size,
            "has_ai_index": bundle_manifest["has_ai_index"],
            "has_pmtiles": bundle_manifest["has_pmtiles"],
            "generated_at": bundle_manifest["generated_at"],
        }

    # ------------------------- BUILD PAYLOAD -------------------------

    def _build_tour_data_payload(self, tour: Tour) -> Dict[str, Any]:
        """
        Struttura compatibile con quella usata oggi da mobile/offline_tour_service.
        """
        tour_dict = TourSerializer(tour).data
        main_wps = WaypointSerializer(tour.waypoints.all(), many=True).data

        processed_main = [self._augment_waypoint_payload(wp) for wp in main_wps]

        sub_tours_payload: List[Dict[str, Any]] = []
        if tour.category == Category.MIXED:
            for st in tour.sub_tours.all():
                st_waypoints = WaypointSerializer(st.waypoints.all(), many=True).data
                processed_st_wps = [self._augment_waypoint_payload(wp) for wp in st_waypoints]
                sub_tours_payload.append(
                    {
                        "sub_tour": TourSerializer(st).data,
                        "waypoints": processed_st_wps,
                    }
                )

        return {
            "tour": tour_dict,
            "waypoints": processed_main,
            "sub_tours": sub_tours_payload if sub_tours_payload else None,
            "downloaded_at": timezone.now().isoformat(),
            "version": self.BUNDLE_FORMAT_VERSION,
        }

    def _augment_waypoint_payload(self, wp_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Aggiunge i campi offline attesi dal mobile.
        """
        wp_data = dict(wp_data)
        wp_data["local_images"] = []
        wp_data["local_resources"] = {
            "readme": None,
            "links": None,
            "audio": None,
            "video": None,
            "pdf": None,
        }
        return wp_data

    # ------------------------- ZIP ADDERS -------------------------
    
    def _optimized_image_bytes(self, storage_key: str) -> Optional[bytes]:
        try:
            with self.storage.open(storage_key, mode="rb") as src:
                original = src.read()

            with Image.open(io.BytesIO(original)) as img:
                img = ImageOps.exif_transpose(img)

                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                elif img.mode == "L":
                    img = img.convert("RGB")

                img.thumbnail(self.IMAGE_MAX_SIZE, Image.Resampling.LANCZOS)

                out = io.BytesIO()
                img.save(
                    out,
                    format="JPEG",
                    quality=self.IMAGE_JPEG_QUALITY,
                    optimize=True,
                    progressive=True,
                )
                return out.getvalue()

        except (UnidentifiedImageError, OSError) as exc:
            logger.warning("Image optimization failed for %s: %s", storage_key, exc)
            return None

    def _add_tour_default_image(
        self,
        zf: zipfile.ZipFile,
        tour: Tour,
        archive_prefix: Optional[str] = None,
    ) -> Optional[str]:
        if not tour.default_image:
            return None

        src_key = tour.default_image.name
        ext = Path(src_key).suffix or ".jpg"
        arc_name = f"default_image{ext}"
        if archive_prefix:
            arc_name = f"{archive_prefix}/default_image{ext}"

        if self.storage.exists(src_key):
            self._zip_add_storage_key(zf, src_key, arc_name)
            return arc_name

        return None

    def _add_waypoint_to_zip(
        self,
        zf: zipfile.ZipFile,
        waypoint: Waypoint,
        waypoint_prefix: str,
        waypoint_json_record: Optional[Dict[str, Any]],
    ) -> None:
        if waypoint_json_record is None:
            # Non dovrebbe succedere, ma evita crash totale
            logger.warning("Waypoint JSON record not found for waypoint_id=%s", waypoint.id)
            return

        # immagini preferite: ADDITIONAL, fallback 2 DEFAULT
        images_qs = waypoint.images.filter(type_of_images=TypeOfImage.ADDITIONAL_IMAGES)
        if not images_qs.exists():
            images_qs = waypoint.images.filter(type_of_images=TypeOfImage.DEFAULT)[:2]

        local_images: List[str] = []

        for idx, img_obj in enumerate(images_qs):
            if not img_obj.image:
                continue

            src_key = img_obj.image.name
            src_ext = Path(src_key).suffix.lower() or ".jpg"

            arc_rel = f"{waypoint_prefix}/image_{idx}.jpg.zlib"

            if self.storage.exists(src_key):
                optimized = self._optimized_image_bytes(src_key)

                if optimized:
                    zf.writestr(
                        arc_rel,
                        optimized,
                        compress_type=zipfile.ZIP_STORED,
                    )
                else:
                    self._zip_add_storage_key(zf, src_key, arc_rel)

                local_images.append(arc_rel)
                
        waypoint_json_record["local_images"] = local_images

        # resources file fields
        res_map: List[Tuple[str, Any]] = [
            ("readme", waypoint.readme_item),
            ("audio", waypoint.audio_item),
            ("pdf", waypoint.pdf_item),
        ]
        
        if self.INCLUDE_VIDEO_IN_OFFLINE_BUNDLE:
            res_map.append(("video", waypoint.video_item))

        for res_name, field in res_map:
            if not field:
                continue
            src_key = field.name
            ext = Path(src_key).suffix or self._default_extension_for_resource(res_name)
            arc_rel = f"{waypoint_prefix}/{res_name}{ext}"

            if self.storage.exists(src_key):
                self._zip_add_storage_key(zf, src_key, arc_rel)
                waypoint_json_record["local_resources"][res_name] = arc_rel

        # links -> file json
        links = [lnk.link for lnk in waypoint.links.all() if lnk.link]
        if links:
            links_rel = f"{waypoint_prefix}/links.json"
            zf.writestr(
                links_rel,
                json.dumps(links, ensure_ascii=False),
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )
            waypoint_json_record["local_resources"]["links"] = links_rel

    def _zip_add_storage_key(self, zf: zipfile.ZipFile, storage_key: str, arc_name: str) -> None:
        """
        Scarica temporaneamente il file da storage e lo aggiunge nello zip
        con strategia compressione ottimizzata per estensione.
        """
        if not self.storage.exists(storage_key):
            raise OfflineBundleError(f"Storage key not found: {storage_key}")

        with self.storage.open(storage_key, mode="rb") as src:
            data = src.read()

        compress_type, compresslevel = self._compression_for_name(arc_name)
        zf.writestr(
            arc_name,
            data,
            compress_type=compress_type,
            compresslevel=compresslevel,
        )

    def _zip_add_file(self, zf: zipfile.ZipFile, local_path: Path, arc_name: str) -> None:
        compress_type, compresslevel = self._compression_for_name(arc_name)
        with open(local_path, "rb") as f:
            zf.writestr(
                arc_name,
                f.read(),
                compress_type=compress_type,
                compresslevel=compresslevel,
            )

    def _compression_for_name(self, name: str) -> Tuple[int, Optional[int]]:
        ext = Path(name).suffix.lower()
        if ext in self.STORED_EXTENSIONS:
            return zipfile.ZIP_STORED, None
        if ext in self.DEFLATED_EXTENSIONS:
            return zipfile.ZIP_DEFLATED, 9
        # fallback conservativo
        return zipfile.ZIP_DEFLATED, 6

    # ------------------------- STORAGE HELPERS -------------------------

    def _upload_file_to_storage(self, local_path: Path, storage_key: str) -> None:
        with open(local_path, "rb") as f:
            self.storage.save(storage_key, ContentFile(f.read()))

    # ------------------------- QUERY HELPERS -------------------------

    def _get_tour_for_bundle(self, tour_id: int) -> Tour:
        waypoints_prefetch = Prefetch(
            "waypoints",
            queryset=Waypoint.objects.order_by("position", "id").prefetch_related(
                Prefetch("images", queryset=WaypointViewImage.objects.all()),
                Prefetch("links", queryset=WaypointViewLink.objects.all()),
            ),
        )

        qs = (
            Tour.objects.filter(pk=tour_id)
            .prefetch_related(
                waypoints_prefetch,
                Prefetch(
                    "sub_tours",
                    queryset=Tour.objects.order_by("id").prefetch_related(waypoints_prefetch),
                ),
            )
        )

        tour = qs.first()
        if not tour:
            raise OfflineBundleError(f"Tour not found: {tour_id}")

        return tour

    # ------------------------- JSON HELPERS -------------------------

    def _find_waypoint_record(
        self, waypoint_list: List[Dict[str, Any]], waypoint_id: int
    ) -> Optional[Dict[str, Any]]:
        for wp in waypoint_list:
            if int(wp.get("id", -1)) == int(waypoint_id):
                return wp
        return None

    def _default_extension_for_resource(self, resource_name: str) -> str:
        return {
            "readme": ".md",
            "audio": ".mp4",
            "video": ".mp4",
            "pdf": ".pdf",
        }.get(resource_name, ".bin")