import os
import django
import sys
from docx import Document
import subprocess
from pathlib import Path

current_file = Path(__file__).resolve()
project_root = current_file.parent.parent
print(f"project root: {project_root}")
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xr_tour_guide.settings')
django.setup()

from xr_tour_guide_core.models import Tour, Waypoint, WaypointViewImage, Category, CustomUser, TypeOfImage
from django.core.files import File

BASE_PATH = "./san_nilo"
VOICE_MODEL = "./it_IT-riccardo-x_low.onnx"

print("Start - Creating Cammino di San Nilo Tour")

if not Tour.objects.filter(title='Cammino di San Nilo').exists():
    print("Cammino di San Nilo Tour does not exist - Creating...")
    tour_san_nilo = Tour.objects.create(
        title='Cammino di San Nilo',
        subtitle='Da Sapri attraverso il Cilento',
        place='Sapri',
        coordinates="40.071389,15.630556",
        category=Category.MIXED,
        description='Il Cammino di San Nilo attraversa alcuni dei luoghi più suggestivi del Cilento',
        user=CustomUser.objects.get(username='xrtourguide') #firstly register a user, after run this script
    )
    print(f"Tour created: {tour_san_nilo.title}")
else:
    print("Cammino di San Nilo Tour already exists")
    tour_san_nilo = Tour.objects.get(title='Cammino di San Nilo')

print(f"Tour ID: {tour_san_nilo.pk}")

def extract_text_from_docx(docx_path):
    try:
        doc = Document(docx_path)
        full_text = []
        for para in doc.paragraphs:
            full_text.append(para.text)
        return '\n'.join(full_text)
    except Exception as e:
        print(f"Error extracting text from {docx_path}: {e}")
        return ""

def generate_audio_from_text(text, output_path):
    try:
        process = subprocess.run(
            ['piper', '--model', VOICE_MODEL, '--output_file', output_path],
            input=text,
            text=True,
            capture_output=True
        )
        
        if process.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            print(f"Audio generated: {output_path}")
            return True
        else:
            print(f"Error generating audio: {process.stderr}")
            return False
    except Exception as e:
        print(f"Error generating audio: {e}")
        return False

for folder_name in sorted(os.listdir(BASE_PATH)):
    folder_path = os.path.join(BASE_PATH, folder_name)
    
    if not os.path.isdir(folder_path):
        continue
    
    print(f"\n--- Processing waypoint: {folder_name} ---")
    
    description = folder_name
    docx_files = [f for f in os.listdir(folder_path) if f.lower().endswith('.docx') and not f.startswith('~$')]
    audio_path = None
    
    if docx_files:
        docx_path = os.path.join(folder_path, docx_files[0])
        description = extract_text_from_docx(docx_path)
        print(f"Description extracted from: {docx_files[0]}")
        
        audio_filename = 'description.wav'
        audio_path = os.path.join(folder_path, audio_filename)
        
        if generate_audio_from_text(description, audio_path):
            print(f"Audio created: {audio_filename}")
        else:
            audio_path = None
    
    waypoint, created = Waypoint.objects.get_or_create(
        title=folder_name,
        tour=tour_san_nilo,
        defaults={
            "place": "Cilento",
            "coordinates": "40.071389,15.630556",
            "description": description
        }
    )
    
    if created:
        print(f"Waypoint created: {waypoint.title}")
    else:
        print(f"Waypoint already exists: {waypoint.title}")
        if description != folder_name:
            waypoint.description = description
            waypoint.save()
            print("Description updated")
    
    for file_name in os.listdir(folder_path):
        file_path = os.path.join(folder_path, file_name)
        
        if not os.path.isfile(file_path):
            continue
        
        if file_name.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            print(f"Adding image: {file_name}")
            with open(file_path, 'rb') as img_file:
                WaypointViewImage.objects.create(
                    waypoint=waypoint,
                    image=File(img_file, name=file_name),
                    type_of_images=TypeOfImage.DEFAULT
                )
        
        elif file_name.lower() == "readme.md":
            print(f"Adding readme: {file_name}")
            with open(file_path, 'rb') as readme_file:
                waypoint.readme_item.save(file_name, File(readme_file))
        
        elif file_name.lower().endswith((".mp3", ".wav")) and audio_path and file_path == audio_path:
            print(f"Adding generated audio: {file_name}")
            with open(file_path, 'rb') as audio_file:
                waypoint.audio_item.save(file_name, File(audio_file))
        
        elif file_name.lower().endswith((".mp4", ".mov", ".mkv")):
            print(f"Adding video: {file_name}")
            with open(file_path, 'rb') as video_file:
                waypoint.video_item.save(file_name, File(video_file))
        
        elif file_name.lower().endswith(".pdf"):
            print(f"Adding PDF: {file_name}")
            with open(file_path, 'rb') as pdf_file:
                waypoint.pdf_item.save(file_name, File(pdf_file))

print("\n=== DONE ===")
print(f"Total waypoints: {tour_san_nilo.waypoints.count()}")