import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from datetime import datetime, timezone
import logging

from django.db import transaction
from django.core.files import File
from django.utils.text import slugify
from django.db.models import Prefetch

from ..models import (
    Tour,
    Waypoint,
    WaypointViewImage,
    WaypointViewLink,
    MinioStorage,
    Status,
)

logger = logging.getLogger(__name__)

class TourPortabilityError(Exception):
    pass


class TourPortabilityService:
    
    EXPORT_VERSION = 1
    
    def export_tour(self, tour, include_subtours=True, output_path=None):
        storage = MinioStorage()
        tour = self._get_export_tour(tour.pk if hasattr(tour, "pk") else int(tour), include_subtours)

        if output_path is None:
            export_dir = Path(tempfile.gettempdir()) / "xr_tour_exports"
            export_dir.mkdir(parents=True, exist_ok=True)
            output_path = export_dir / f"tour_export_{slugify(tour.title)}_{int(datetime.now(timezone.utc).timestamp())}.zip"
            
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        manifest = {
            "version": self.EXPORT_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "source": "xr_tour_guide",
            "tour": self._serialize_tour_fields(tour),
            "waypoints": [],
            "subtours": [],
        }

        with zipfile.ZipFile(
            output_path,
            "w",
            compression=zipfile.ZIP_STORED,
            allowZip64=True,
            compresslevel=1,
        ) as zf:
            # cover image
            if tour.default_image:
                archive_name = f"files/tour/{Path(tour.default_image.name).name}"
                written = self._write_storage_file_to_zip(
                    storage,
                    tour.default_image.name,
                    zf,
                    archive_name,
                )
                if written:
                    manifest["tour"]["default_image"] = archive_name

            # waypoints
            for idx, waypoint in enumerate(tour.waypoints.all(), start=1):
                wp_data = self._serialize_waypoint_fields(waypoint)
                wp_prefix = Path("files/waypoints") / f"{idx:04d}"

                for img_idx, image in enumerate(waypoint.images.all(), start=1):
                    if not image.image:
                        continue
                    ext = Path(image.image.name).suffix or ".bin"
                    archive_name = (wp_prefix / "images" / f"{img_idx:02d}{ext}").as_posix()

                    written = self._write_storage_file_to_zip(
                        storage,
                        image.image.name,
                        zf,
                        archive_name,
                    )
                    if written:
                        wp_data["images"].append({
                            "type": image.type_of_images,
                            "path": archive_name,
                        })

                resources_map = {
                    "pdf": waypoint.pdf_item,
                    "audio": waypoint.audio_item,
                    "video": waypoint.video_item,
                    "readme": waypoint.readme_item,
                }

                for key, field_file in resources_map.items():
                    if not field_file:
                        continue

                    ext = Path(field_file.name).suffix or ".bin"
                    archive_name = (wp_prefix / "resources" / f"{key}{ext}").as_posix()

                    written = self._write_storage_file_to_zip(
                        storage,
                        field_file.name,
                        zf,
                        archive_name,
                    )
                    if written:
                        wp_data["resources"][key] = archive_name

                wp_data["links"] = [link.link for link in waypoint.links.all() if link.link]
                manifest["waypoints"].append(wp_data)

            # subtours
            if include_subtours:
                for sub_tour in tour.sub_tours.all():
                    sub_manifest = {
                        "tour": self._serialize_tour_fields(sub_tour),
                        "waypoints": [],
                    }

                    if sub_tour.default_image:
                        archive_name = (
                            Path("files/subtours")
                            / slugify(sub_tour.title or str(sub_tour.pk))
                            / "tour"
                            / Path(sub_tour.default_image.name).name
                        ).as_posix()

                        written = self._write_storage_file_to_zip(
                            storage,
                            sub_tour.default_image.name,
                            zf,
                            archive_name,
                        )
                        if written:
                            sub_manifest["tour"]["default_image"] = archive_name

                    for idx, waypoint in enumerate(sub_tour.waypoints.all(), start=1):
                        wp_data = self._serialize_waypoint_fields(waypoint)
                        wp_prefix = (
                            Path("files/subtours")
                            / slugify(sub_tour.title or str(sub_tour.pk))
                            / "waypoints"
                            / f"{idx:04d}"
                        )

                        for img_idx, image in enumerate(waypoint.images.all(), start=1):
                            if not image.image:
                                continue
                            ext = Path(image.image.name).suffix or ".bin"
                            archive_name = (wp_prefix / "images" / f"{img_idx:02d}{ext}").as_posix()

                            written = self._write_storage_file_to_zip(
                                storage,
                                image.image.name,
                                zf,
                                archive_name,
                            )
                            if written:
                                wp_data["images"].append({
                                    "type": image.type_of_images,
                                    "path": archive_name,
                                })

                        resources_map = {
                            "pdf": waypoint.pdf_item,
                            "audio": waypoint.audio_item,
                            "video": waypoint.video_item,
                            "readme": waypoint.readme_item,
                        }

                        for key, field_file in resources_map.items():
                            if not field_file:
                                continue

                            ext = Path(field_file.name).suffix or ".bin"
                            archive_name = (wp_prefix / "resources" / f"{key}{ext}").as_posix()

                            written = self._write_storage_file_to_zip(
                                storage,
                                field_file.name,
                                zf,
                                archive_name,
                            )
                            if written:
                                wp_data["resources"][key] = archive_name

                        wp_data["links"] = [link.link for link in waypoint.links.all() if link.link]
                        sub_manifest["waypoints"].append(wp_data)

                    manifest["subtours"].append(sub_manifest)

            zf.writestr(
                "manifest.json",
                json.dumps(manifest, indent=2, ensure_ascii=False),
                compress_type=zipfile.ZIP_DEFLATED,
            )

        return str(output_path)
            
    @transaction.atomic
    def import_tour(self, archive_file, owner=None, create_copy=True):
        temp_dir = Path(tempfile.mkdtemp(prefix="tour_import_"))
        try:
            with zipfile.ZipFile(archive_file) as zf:
                self._safe_extract_zip(zf, temp_dir)

            manifest_path = temp_dir / "manifest.json"
            if not manifest_path.exists():
                raise TourPortabilityError("manifest.json not found")

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            if manifest.get("version") != self.EXPORT_VERSION:
                raise TourPortabilityError("Unsupported export version")

            tour_data = manifest["tour"]
            title = tour_data["title"]
            if create_copy:
                title = self._build_imported_title(title)

            tour = Tour(
                title=title,
                subtitle=tour_data.get("subtitle"),
                place=tour_data["place"],
                coordinates=tour_data["coordinates"],
                category=tour_data["category"],
                language=tour_data.get("language", "it"),
                description=tour_data.get("description"),
                user=owner,
                status=Status.READY,
                tot_view=0,
                reports=0,
                is_subtour=False,
            )
            tour.save()

            # cover image
            if tour_data.get("default_image"):
                default_image_path = temp_dir / tour_data["default_image"]
                if default_image_path.exists():
                    with open(default_image_path, "rb") as f:
                        tour.default_image.save(default_image_path.name, File(f), save=False)
                    tour.save()

            # waypoints
            for wp_data in manifest.get("waypoints", []):
                waypoint = Waypoint.objects.create(
                    tour=tour,
                    position=wp_data.get("position", 0),
                    title=wp_data["title"],
                    place=wp_data.get("place"),
                    coordinates=wp_data["coordinates"],
                    description=wp_data.get("description"),
                    is_preliminary_info=wp_data.get("is_preliminary_info", False)
                )

                # resources
                resources = wp_data.get("resources", {})
                resource_field_map = {
                    "pdf": "pdf_item",
                    "audio": "audio_item",
                    "video": "video_item",
                    "readme": "readme_item",
                }
                for key, field_name in resource_field_map.items():
                    rel_path = resources.get(key)
                    if rel_path:
                        source = temp_dir / rel_path
                        if source.exists():
                            with open(source, "rb") as f:
                                getattr(waypoint, field_name).save(source.name, File(f), save=False)
                waypoint.save()

                # images
                for img in wp_data.get("images", []):
                    rel_path = img.get("path")
                    if not rel_path:
                        continue
                    source = temp_dir / rel_path
                    if source.exists():
                        with open(source, "rb") as f:
                            WaypointViewImage.objects.create(
                                waypoint=waypoint,
                                image=File(f, name=source.name),
                                type_of_images=img.get("type", "DEFAULT"),
                            )

                # links
                links_to_create = [
                    WaypointViewLink(waypoint=waypoint, link=link)
                    for link in wp_data.get("links", [])
                    if link
                ]
                if links_to_create:
                        WaypointViewLink.objects.bulk_create(links_to_create, batch_size=500)

            # subtours
            for sub_data in manifest.get("subtours", []):
                sub_tour_data = sub_data["tour"]
                sub_title = sub_tour_data["title"]
                if create_copy:
                    sub_title = self._build_imported_title(sub_title)

                sub_tour = Tour(
                    title=sub_title,
                    subtitle=sub_tour_data.get("subtitle"),
                    place=sub_tour_data["place"],
                    coordinates=sub_tour_data["coordinates"],
                    category=sub_tour_data["category"],
                    language=sub_tour_data.get("language", tour.language),
                    description=sub_tour_data.get("description"),
                    user=owner,
                    status=Status.READY,
                    tot_view=0,
                    reports=0,
                    is_subtour=True,
                )
                sub_tour.save()

                if sub_tour_data.get("default_image"):
                    default_image_path = temp_dir / sub_tour_data["default_image"]
                    if default_image_path.exists():
                        with open(default_image_path, "rb") as f:
                            sub_tour.default_image.save(default_image_path.name, File(f), save=False)
                        sub_tour.save()

                for wp_data in sub_data.get("waypoints", []):
                    waypoint = Waypoint.objects.create(
                        tour=sub_tour,
                        position=wp_data.get("position", 0),
                        title=wp_data["title"],
                        place=wp_data.get("place"),
                        coordinates=wp_data["coordinates"],
                        description=wp_data.get("description"),
                        is_preliminary_info=wp_data.get("is_preliminary_info", False)
                    )

                    resources = wp_data.get("resources", {})
                    resource_field_map = {
                        "pdf": "pdf_item",
                        "audio": "audio_item",
                        "video": "video_item",
                        "readme": "readme_item",
                    }
                    for key, field_name in resource_field_map.items():
                        rel_path = resources.get(key)
                        if rel_path:
                            source = temp_dir / rel_path
                            if source.exists():
                                with open(source, "rb") as f:
                                    getattr(waypoint, field_name).save(source.name, File(f), save=False)
                    waypoint.save()

                    for img in wp_data.get("images", []):
                        rel_path = img.get("path")
                        if not rel_path:
                            continue
                        source = temp_dir / rel_path
                        if source.exists():
                            with open(source, "rb") as f:
                                WaypointViewImage.objects.create(
                                    waypoint=waypoint,
                                    image=File(f, name=source.name),
                                    type_of_images=img.get("type", "DEFAULT"),
                                )

                    links_to_create = [
                        WaypointViewLink(waypoint=waypoint, link=link)
                        for link in wp_data.get("links", [])
                        if link
                    ]
                    if links_to_create:
                            WaypointViewLink.objects.bulk_create(links_to_create, batch_size=500)


                tour.sub_tours.add(sub_tour)

            return tour

        except zipfile.BadZipFile as exc:
            raise TourPortabilityError("Invalid ZIP archive") from exc
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def _copy_storage_file(self, storage, source_name, destination_path):
        if not source_name:
            return None
        if not storage.exists(source_name):
            return None
        
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        
        with storage.open(source_name, 'rb') as src, open(destination_path, 'wb') as dst:
            shutil.copyfileobj(src, dst)
            
        return str(destination_path)
    
    def _serialize_tour_fields(self, tour):
        return {
            "title": tour.title,
            "subtitle": tour.subtitle, 
            "place": tour.place,
            "description": tour.description,
            "coordinates": tour.coordinates,
            "category": tour.category,
            "language": tour.language,
            "default_image": None,
        }
        
    def _serialize_waypoint_fields(self, waypoint):
        return {
            "position": waypoint.position,
            "title": waypoint.title,
            "description": waypoint.description,
            "coordinates": waypoint.coordinates,
            "place": waypoint.place,
            "is_preliminary_info": waypoint.is_preliminary_info,
            "images": [],
            "links": [],
            "resources": {
                "pdf": None,
                "audio": None,
                "video": None,
                "readme": None,
            },
        }
        
    def _build_imported_title(self, title):
        return f"{title} (Imported)"
    
    def _safe_extract_zip(self, zip_file, target_dir):
        target_dir = Path(target_dir).resolve()
        
        for member in zip_file.infolist():
            member_path = (target_dir / member.filename).resolve()
            if not str(member_path).startswith(str(target_dir)):
                raise TourPortabilityError(f"Unsafe file path detected in ZIP: {member.filename}")
            zip_file.extract(member, target_dir)
            
    def _waypoint_export_queryset(self):
        return Waypoint.objects.order_by("position", "id").prefetch_related(
            Prefetch("images", queryset=WaypointViewImage.objects.order_by("id")),
            Prefetch("links", queryset=WaypointViewLink.objects.order_by("id")),
        )
        
    def _get_export_tour(self, tour_id, include_subtours=True):
        qs = Tour.objects.prefetch_related(
            Prefetch("waypoints", queryset=self._waypoint_export_queryset())
        )
        
        if include_subtours:
            subtour_qs = Tour.objects.order_by("id").prefetch_related(
                Prefetch("waypoints", queryset=self._waypoint_export_queryset())
            )
            qs = qs.prefetch_related(Prefetch("sub_tours", queryset=subtour_qs))
            
        return qs.get(pk=tour_id)
    
    def _compression_for_filename(self, filename):
        ext = Path(filename).suffix.lower()
        if ext in {
            ".jpg", ".jpeg", ".png", ".gif", ".webp",
            ".mp4", ".mkv", ".mov",
            ".mp3", ".wav",
            ".pdf", ".zip"
        }:
            return zipfile.ZIP_STORED
        return zipfile.ZIP_DEFLATED
    
    def _write_storage_file_to_zip(self, storage, source_name, zf, archive_name):
        if not source_name:
            return None
        
        try:
            with storage.open(source_name, 'rb') as src:
                info = zipfile.ZipInfo(archive_name)
                info.compress_type = self._compression_for_filename(source_name)
                info.date_time = datetime.now(timezone.utc).timetuple()[:6]
                
                with zf.open(info, 'w') as dst:
                    shutil.copyfileobj(src, dst, length=1024*1024)
                    
            return archive_name
        except Exception as exc:
            logger.warning('Skipping export file %s: %s', source_name, exc)
            return None
        
    