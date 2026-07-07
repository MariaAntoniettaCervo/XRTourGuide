import os
import sys
import django
from docx import Document
from pathlib import Path

current_file = Path(__file__).resolve()
project_root = current_file.parent.parent
print(f"project root: {project_root}")
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xr_tour_guide.settings')
django.setup()

from xr_tour_guide_core.models import (
    Tour,
    Waypoint,
    WaypointViewImage,
    WaypointViewLink,
    Category,
    CustomUser,
    TypeOfImage
)
from django.core.files import File
from django.db import connection

TOUR_CONFIG = {
    "title": "Morigerati",
    "subtitle": "Tour dei Mestieri e della Cereria",
    "place": "Morigerati",
    "coordinates": "40.142222,15.552778",
    "category": Category.INDOOR,
    "description": "Tour dedicato agli antichi mestieri e alla cereria di Morigerati",
    "username": "xrtourguide"
}

BASE_PATH = "./morigerati_tour"
DEFAULT_IMAGE_NAME = "default_img.jpeg"


def fix_auto_increment():
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT MAX(id) FROM Tour")
            max_id = cursor.fetchone()[0]
            if max_id is None:
                max_id = 0
            next_id = max_id + 1
            cursor.execute(f"ALTER TABLE Tour AUTO_INCREMENT = {next_id}")
    except Exception:
        pass


def extract_text_from_docx(docx_path):
    try:
        doc = Document(docx_path)
        text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        if text:
            return text
    except Exception:
        try:
            with open(docx_path, "r", encoding="utf-8") as f:
                text = f.read().strip()
                if text:
                    return text
        except Exception:
            pass
    return ""


def create_tour(config, base_path):
    try:
        user = CustomUser.objects.get(username=config["username"])
    except CustomUser.DoesNotExist:
        sys.exit(1)
    
    try:
        tour = Tour.objects.get(title=config["title"])
    except Tour.DoesNotExist:
        fix_auto_increment()
        tour = Tour(
            title=config["title"],
            subtitle=config["subtitle"],
            place=config["place"],
            coordinates=config["coordinates"],
            category=config["category"],
            description=config["description"],
            user=user
        )
        default_img_path = os.path.join(base_path, DEFAULT_IMAGE_NAME)
        if os.path.exists(default_img_path):
            with open(default_img_path, "rb") as f:
                tour.default_image.save(DEFAULT_IMAGE_NAME, File(f), save=False)
        tour.save()
    
    return tour


def process_waypoints(tour, base_path):
    waypoint_count = 0
    folders = []
    
    for folder_name in os.listdir(base_path):
        folder_path = os.path.join(base_path, folder_name)
        if not os.path.isdir(folder_path) or folder_name.startswith('.'):
            continue
        if folder_name.endswith(('.jpeg', '.jpg', '.png')):
            continue
        folders.append(folder_name)
    
    folders.sort()
    
    for folder_name in folders:
        folder_path = os.path.join(base_path, folder_name)
        description = folder_name
        docx_path = os.path.join(folder_path, "descrizione.docx")
        
        if os.path.exists(docx_path):
            extracted_desc = extract_text_from_docx(docx_path)
            if extracted_desc:
                description = extracted_desc
        
        waypoint, created = Waypoint.objects.get_or_create(
            title=folder_name,
            tour=tour,
            defaults={
                "place": tour.place,
                "coordinates": tour.coordinates,
                "description": description
            }
        )
        
        if not created:
            waypoint.description = description
            waypoint.save()
        
        process_waypoint_files(waypoint, folder_path)
        process_images(waypoint, folder_path, "img", TypeOfImage.DEFAULT)
        process_images(waypoint, folder_path, "additional_img", TypeOfImage.ADDITIONAL_IMAGES)
        waypoint_count += 1
    
    return waypoint_count


def process_waypoint_files(waypoint, folder_path):
    for file_name in os.listdir(folder_path):
        file_path = os.path.join(folder_path, file_name)
        if os.path.isdir(file_path):
            continue
        if file_name.lower() == "descrizione.docx":
            continue
        
        if file_name.lower() == "readme.md":
            with open(file_path, "rb") as f:
                waypoint.readme_item.save(file_name, File(f))
        elif file_name.lower().endswith((".mp4", ".mov", ".mkv")):
            with open(file_path, "rb") as f:
                waypoint.video_item.save(file_name, File(f))
        elif file_name.lower().endswith(".pdf"):
            with open(file_path, "rb") as f:
                waypoint.pdf_item.save(file_name, File(f))
        elif file_name.lower().endswith((".mp3", ".wav")):
            with open(file_path, "rb") as f:
                waypoint.audio_item.save(file_name, File(f))
        elif file_name.lower() == "links.txt":
            process_links(waypoint, file_path)


def process_links(waypoint, links_file):
    try:
        with open(links_file, "r", encoding="utf-8") as f:
            links = [line.strip() for line in f.readlines() if line.strip()]
        for link in links:
            WaypointViewLink.objects.get_or_create(waypoint=waypoint, link=link)
    except Exception:
        pass


def process_images(waypoint, folder_path, img_folder_name, image_type):
    img_folder = os.path.join(folder_path, img_folder_name)
    if not os.path.exists(img_folder):
        return
    
    for img_name in sorted(os.listdir(img_folder)):
        img_path = os.path.join(img_folder, img_name)
        if img_name.lower().endswith((".jpg", ".jpeg", ".png")):
            existing = WaypointViewImage.objects.filter(
                waypoint=waypoint,
                type_of_images=image_type,
                image__contains=img_name
            ).exists()
            
            if not existing:
                with open(img_path, "rb") as img_file:
                    WaypointViewImage.objects.create(
                        waypoint=waypoint,
                        image=File(img_file, name=img_name),
                        type_of_images=image_type
                    )


def main():
    if not os.path.exists(BASE_PATH):
        sys.exit(1)
    
    tour = create_tour(TOUR_CONFIG, BASE_PATH)
    waypoint_count = process_waypoints(tour, BASE_PATH)
    
    print(f"Tour: {tour.title} (ID: {tour.pk})")
    print(f"Waypoint creati/aggiornati: {waypoint_count}")
    print(f"Totale waypoint: {tour.waypoints.count()}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)