import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xr_tour_guide.settings')
django.setup()

from xr_tour_guide_core.models import Tour, Waypoint, WaypointViewImage, Category, CustomUser
from django.core.files import File
from django.core.files.base import ContentFile

BASE_PATH = "unisa_file"

print("Starting import process")

if not Tour.objects.filter(title='Unisa').exists():
    print("Tour 'Unisa' does not exist - creating new tour")
    tour_unisa = Tour.objects.create(
        title='Unisa',
        subtitle='University of Salerno',
        place='Fisciano',
        coordinates="40.767715,14.792072",
        category=Category.MIXED,
        description='Fisciano Campus',
        user=CustomUser.objects.get(username='username')
    )
    print("Successfully created tour 'Unisa'")
else:
    print("Tour 'Unisa' already exists - loading existing tour")
    tour_unisa = Tour.objects.get(title='Unisa')

main_coords = tour_unisa.coordinates
print(f"Tour ID: {tour_unisa.pk}, Title: {tour_unisa.title}")
print(f"Main coordinates: {main_coords}")

print(f"Scanning base path: {BASE_PATH}")
for folder_name in os.listdir(BASE_PATH):
    folder_path = os.path.join(BASE_PATH, folder_name)
    if not os.path.isdir(folder_path):
        print(f"Skipping '{folder_name}' - not a directory")
        continue

    print(f"\nProcessing folder: {folder_name}")

    if folder_name.lower().startswith("interno"):
        print(f"Detected internal tour folder: {folder_name}")
        if Tour.objects.filter(title=f"{tour_unisa.title} - {folder_name}").exists():
            print(f"Subtour '{folder_name}' already exists - loading existing")
            sub_tour = Tour.objects.get(title=f"{tour_unisa.title} - {folder_name}")
        else:
            print(f"Creating new subtour: {folder_name}")
            sub_tour = Tour.objects.create(
                title=f"{tour_unisa.title} - {folder_name}",
                subtitle=None,
                place=tour_unisa.place,
                coordinates=tour_unisa.coordinates,
                category=Category.INDOOR,
                description=f"Subtour {folder_name}",
                user=tour_unisa.user,
                is_subtour=True,
            )
            print(f"Successfully created subtour with ID: {sub_tour.pk}")

        print(f"Linking subtour to main tour")
        tour_unisa.sub_tours.add(sub_tour)

        print(f"Processing waypoints for subtour '{folder_name}'")
        interno_path = folder_path
        for w_name in os.listdir(interno_path):
            wp_folder = os.path.join(interno_path, w_name)
            if not os.path.isdir(wp_folder):
                print(f"Skipping '{w_name}' in subtour - not a directory")
                continue

            print(f"Creating waypoint: {w_name}")
            waypoint = Waypoint.objects.create(
                title=w_name,
                tour=sub_tour,
                place="Fisciano",
                coordinates=main_coords,
                description=w_name
            )
            print(f"Created waypoint '{w_name}' with ID: {waypoint.pk}")

            data_path = os.path.join(wp_folder, "data")
            if not os.path.exists(data_path):
                print(f"No 'data' folder found for waypoint '{w_name}' - skipping files")
                continue

            print(f"Processing files for waypoint '{w_name}'")
            for root, dirs, files in os.walk(data_path):
                for f in files:
                    file_path = os.path.join(root, f)
                    if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                        print(f"Adding image: {f}")
                        with open(file_path, 'rb') as img_file:
                            WaypointViewImage.objects.create(waypoint=waypoint, image=File(img_file))
                    elif f.lower().endswith((".mp3", ".wav")):
                        print(f"Adding audio: {f}")
                        with open(file_path, 'rb') as audio_file:
                            waypoint.audio_item.save(f"audio/{f}", File(audio_file))
                    elif f.lower().endswith((".mp4", ".mov", ".mkv")):
                        print(f"Adding video: {f}")
                        with open(file_path, 'rb') as video_file:
                            waypoint.video_item.save(f"video/{f}", File(video_file))
                    elif f.lower().endswith(".pdf"):
                        print(f"Adding PDF: {f}")
                        with open(file_path, 'rb') as pdf_file:
                            waypoint.pdf_item.save(f"pdf/{f}", File(pdf_file))
                    elif f.lower() == "readme.md":
                        print(f"Adding README: {f}")
                        with open(file_path, "rb") as readme_file:
                            waypoint.readme_item.save(f"readme/{f}", File(readme_file))

    print(f"Creating or retrieving waypoint for main tour: {folder_name}")
    waypoint, created = Waypoint.objects.get_or_create(
        title=folder_name,
        tour=tour_unisa,
        defaults={
            "place": "Fisciano",
            "coordinates": main_coords,
            "description": folder_name
        }
    )
    if created:
        print(f"Created new waypoint '{folder_name}' with ID: {waypoint.pk}")
    else:
        print(f"Waypoint '{folder_name}' already exists with ID: {waypoint.pk}")

    data_path = os.path.join(folder_path, "data")
    if not os.path.exists(data_path):
        print(f"No 'data' folder found for waypoint '{folder_name}' - skipping files")
        continue

    print(f"Processing files for waypoint '{folder_name}'")
    for root, dirs, files in os.walk(data_path):
        for f in files:
            file_path = os.path.join(root, f)
            print(f"Processing file: {file_path}")
            filename = os.path.basename(f)
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                print(f"Adding image: {filename}")
                with open(file_path, 'rb') as img_file:
                    WaypointViewImage.objects.create(
                        waypoint=waypoint,
                        image=File(img_file, name=filename)
                    )
            elif f.lower().endswith((".mp3", ".wav")):
                print(f"Adding audio: {filename}")
                with open(file_path, 'rb') as audio_file:
                    waypoint.audio_item.save(filename, File(audio_file))
            elif f.lower().endswith((".mp4", ".mov", ".mkv")):
                print(f"Adding video: {filename}")
                with open(file_path, 'rb') as video_file:
                    waypoint.video_item.save(f"video/{filename}", File(video_file))
            elif f.lower().endswith(".pdf"):
                print(f"Adding PDF: {filename}")
                with open(file_path, 'rb') as pdf_file:
                    waypoint.pdf_item.save(f"audio/{filename}", File(pdf_file))
            elif f.lower() == "readme.md":
                print(f"Adding README: {filename}")
                with open(file_path, "rb") as readme_file:
                    waypoint.readme_item.save(f"readme/{filename}", File(readme_file))

print("\nImport process COMPLETED successfully")