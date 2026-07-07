from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from ...models import Tour, Waypoint, WaypointViewImage
from PIL import Image, ImageDraw
from io import BytesIO

def create_dummy_image(idx_wp, idx_img):
    img = Image.new("RGB", (400, 300), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle((50, 50, 350, 250), fill=(200, 200, 255), outline="blue")
    draw.text((60, 120), f"WP {idx_wp} - IMG {idx_img}", fill="black")
    buffer = BytesIO()
    img.save(buffer, format="JPEG")
    buffer.seek(0)
    return ContentFile(buffer.read(), name=f"image_{idx_wp}_{idx_img}.jpg")

User = get_user_model()

class Command(BaseCommand):
    help = 'Create a mixed tour with waypoint and internal sub-tour'

    def handle(self, *args, **kwargs):
        user, created = User.objects.get_or_create(
            username='groot',
            defaults={
                'email': 'root@example.com',
                'is_superuser': True,
                'is_staff': True
            }
        )
        if created:
            user.set_password('groot')
            user.save()
            self.stdout.write(self.style.SUCCESS("Utente root creato e promosso a superuser"))
        else:
            self.stdout.write("Utente root già esistente")

        main_tour_title = "Tour Mixed 1"
        tour = Tour.objects.filter(title=main_tour_title).first()
        if not tour:
            dummy_content = ContentFile(b"image content here", name="test_image.jpg")
            tour = Tour.objects.create(
                title=main_tour_title,
                subtitle="Sub 4",
                place="Place D",
                category="MIXED",
                description="Descrizione di esempio per tour misto",
                user=user,
                coordinates="41.9028,12.4964",
                default_image=dummy_content
            )
            self.stdout.write(self.style.SUCCESS(f"Creato tour misto: {tour.title}"))
        else:
            self.stdout.write(f"Tour misto già esistente: {tour.title}")

        waypoint = Waypoint.objects.filter(tour=tour).first()
        if not waypoint:
            waypoint = Waypoint.objects.create(
                title=f"Waypoint principale - {tour.title}",
                tour=tour,
                coordinates="41.9028,12.4964",
                description="Descrizione del waypoint principale",
                model_path="model.obj"
            )
            self.stdout.write(self.style.SUCCESS(f"  Creato waypoint: {waypoint.title}"))

            for idx_img in range(2):
                dummy_img = create_dummy_image(1, idx_img)
                image = WaypointViewImage(waypoint=waypoint)
                image.save()
                image.image.save(f"dummy_image_1_{idx_img}.jpg", dummy_img)
                image.save()
                self.stdout.write(f"    Immagine creata: {image.image.name}")
        else:
            self.stdout.write(f"Waypoint già esistente: {waypoint.title}")

        sub_tour_title = "Tour Interno 1 per Mixed"
        sub_tour = Tour.objects.filter(title=sub_tour_title).first()
        if not sub_tour:
            sub_tour = Tour.objects.create(
                title=sub_tour_title,
                subtitle="Sub Interno",
                place="Place D Interno",
                category="INDOOR",
                description="Questo è il sub-tour interno collegato al tour misto",
                user=user,
                coordinates="41.9028,12.4964",
            )
            self.stdout.write(self.style.SUCCESS(f"  Creato sub-tour interno: {sub_tour.title}"))
        else:
            self.stdout.write(f"Sub-tour già esistente: {sub_tour.title}")

        if not tour.sub_tours.filter(id=sub_tour.id).exists():
            tour.sub_tours.add(sub_tour)
            self.stdout.write(self.style.SUCCESS(f"  Sub-tour '{sub_tour.title}' collegato al tour misto"))
        else:
            self.stdout.write(f"  Sub-tour '{sub_tour.title}' già collegato al tour misto")

        existing_wps = Waypoint.objects.filter(tour=sub_tour)
        if existing_wps.exists():
            self.stdout.write(f"  Waypoints già esistenti per il sub-tour: {sub_tour.title}")
        else:
            for idx_wp in range(2):
                wp = Waypoint.objects.create(
                    title=f"Waypoint {idx_wp + 1} - {sub_tour.title}",
                    tour=sub_tour,
                    coordinates="41.9028,12.4964",
                    description=f"Descrizione waypoint {idx_wp + 1} per sub-tour",
                    model_path="model.obj"
                )
                self.stdout.write(self.style.SUCCESS(f"    Creato waypoint per sub-tour: {wp.title}"))

                for idx_img in range(2):
                    dummy_img = create_dummy_image(idx_wp + 1, idx_img)
                    image = WaypointViewImage(waypoint=wp)
                    image.save()
                    image.image.save(f"dummy_image_sub_{idx_wp + 1}_{idx_img}.jpg", dummy_img)
                    image.save()
                    self.stdout.write(f"      Immagine creata: {image.image.name}")
