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

BASE_PATH = "./local_product"
USERNAME = "xrtourguide"
PLACE = "Cilento"
COORDINATES = "40.142222,15.552778"
TOUR_TITLE = "Local Product"


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
        pass
    return ""


def extract_text_from_md(md_path):
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            text = f.read().strip()
            if text:
                return text
    except Exception:
        pass
    return ""


def get_default_image(base_path):
    for folder_name in sorted(os.listdir(base_path)):
        folder_path = os.path.join(base_path, folder_name)
        if os.path.isdir(folder_path) and not folder_name.startswith('.'):
            img_folder = os.path.join(folder_path, "img")
            if os.path.exists(img_folder):
                for img_name in sorted(os.listdir(img_folder)):
                    if img_name.lower().endswith((".jpg", ".jpeg", ".png")):
                        return os.path.join(img_folder, img_name)
    return None


def create_main_tour(user):
    try:
        tour = Tour.objects.get(title=TOUR_TITLE, category=Category.GUIDE)
        print(f"  Tour '{TOUR_TITLE}' already exists")
    except Tour.DoesNotExist:
        fix_auto_increment()
        tour = Tour(
            title=TOUR_TITLE,
            subtitle=f"Typical Products of {PLACE}",
            place=PLACE,
            coordinates=COORDINATES,
            category=Category.GUIDE,
            description=f"A collection of typical products from {PLACE}",
            user=user
        )
        
        default_img_path = get_default_image(BASE_PATH)
        if default_img_path and os.path.exists(default_img_path):
            with open(default_img_path, "rb") as f:
                img_name = os.path.basename(default_img_path)
                tour.default_image.save(img_name, File(f), save=False)
        
        tour.save()
        print(f"  Tour '{TOUR_TITLE}' created with ID: {tour.pk}")
    
    return tour


def create_waypoint_for_product(tour, product_name, product_path):
    description = product_name
    docx_path = os.path.join(product_path, "descrizione.docx")
    md_path = os.path.join(product_path, "descrizione.md")
    
    if os.path.exists(docx_path):
        extracted_desc = extract_text_from_docx(docx_path)
        if extracted_desc:
            description = extracted_desc
    elif os.path.exists(md_path):
        extracted_desc = extract_text_from_md(md_path)
        if extracted_desc:
            description = extracted_desc
    
    waypoint, created = Waypoint.objects.get_or_create(
        title=product_name,
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
    
    process_waypoint_files(waypoint, product_path)
    
    process_images(waypoint, product_path, "img", TypeOfImage.DEFAULT)
    process_images(waypoint, product_path, "additional_img", TypeOfImage.ADDITIONAL_IMAGES)
    
    return waypoint


def process_waypoint_files(waypoint, folder_path):
    for file_name in os.listdir(folder_path):
        file_path = os.path.join(folder_path, file_name)
        if os.path.isdir(file_path):
            continue
        if file_name.lower() in ["descrizione.docx", "descrizione.md"]:
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
        print(f"Error: folder {BASE_PATH} does not exist")
        sys.exit(1)
    
    try:
        user = CustomUser.objects.get(username=USERNAME)
    except CustomUser.DoesNotExist:
        print(f"Error: user '{USERNAME}' not found")
        sys.exit(1)
    
    product_folders = []
    for folder_name in os.listdir(BASE_PATH):
        folder_path = os.path.join(BASE_PATH, folder_name)
        if os.path.isdir(folder_path) and not folder_name.startswith('.'):
            product_folders.append((folder_name, folder_path))
    
    product_folders.sort()
    
    print(f"\nCreating tour '{TOUR_TITLE}' with {len(product_folders)} waypoints...\n")
    
    tour = create_main_tour(user)
    
    total_waypoints = 0
    
    for product_name, product_path in product_folders:
        print(f"Processing: {product_name}")
        
        waypoint = create_waypoint_for_product(tour, product_name, product_path)
        total_waypoints += 1
        
        print(f"  Completed\n")
    
    print("=" * 60)
    print(f"Summary:")
    print(f"  Tour: {TOUR_TITLE}")
    print(f"  Waypoints created/updated: {total_waypoints}")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nOperation interrupted by user")
        sys.exit(1)
    except Exception as e:
        import traceback
        print("\n\nError during execution:")
        traceback.print_exc()
        sys.exit(1)