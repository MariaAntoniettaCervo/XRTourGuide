import requests
from celery import shared_task
from xr_tour_guide_core.models import Tour, MinioStorage, Status, TypeOfImage
from django.core.mail import send_mail
import os
import redis
from redis.lock import Lock
from dotenv import load_dotenv
from django.utils import timezone
from datetime import timedelta
from django.core.files.base import ContentFile
from django.contrib.auth import get_user_model

load_dotenv()

redis_client = redis.StrictRedis.from_url(os.getenv("REDIS_URL", "redis://redis:6379"))

@shared_task(bind=True, max_retries=20, default_retry_delay=10)
def call_api_and_save(self, tour_id):
    storage = MinioStorage()
    response = None
    lock = Lock(redis_client, "build_lock", timeout=24 * 60 * 60)

    try:
        tour = Tour.objects.get(pk=tour_id)
        print("Tour:", tour.pk, tour.title)

        print("Tentativo di acquisizione lock...")
        try:
            acquired = lock.acquire(blocking=True, blocking_timeout=24 * 60 * 60)
            print(f"Acquired: {acquired}")
            if not acquired:
                print(f"Could not acquire lock for tour {tour}, retrying...")
                raise self.retry(exc=Exception("Could not acquire build lock"), countdown=10)
        except Exception as lock_error:
            print(f"Errore nell'acquisizione del lock: {lock_error}")
            raise self.retry(exc=lock_error, countdown=10)
        
        print("Lock acquisito, procedo con la build...")
        waypoints_gps = []
        try:
            storage = MinioStorage()
            if not storage.exists(f"{tour.pk}/data/"):
                storage.save(f"{tour.pk}/data/train/.keep", ContentFile(b""))
                storage.save(f"{tour.pk}/data/test/.keep", ContentFile(b""))
                
            for subtours in tour.sub_tours.all():
                waipoints = subtours.waypoints.filter(is_preliminary_info=False)
                for waypoint in waipoints:
                    num_img = len(waypoint.images.filter(type_of_images=TypeOfImage.DEFAULT.value))
                    if num_img < 5:
                        for i, image in enumerate(waypoint.images.filter(type_of_images=TypeOfImage.DEFAULT.value)):
                            storage.save(f"{tour.pk}/data/train/{waypoint.title}/{image.image.name.split('/')[-1]}", image.image)
                            if i == 1:
                                storage.save(f"{tour.pk}/data/test/{waypoint.title}/{image.image.name.split('/')[-1]}", image.image)
                    else:
                        train = int(num_img * 0.8)
                        test = num_img - train
                        for image in waypoint.images.filter(type_of_images=TypeOfImage.DEFAULT.value)[:train]:
                            storage.save(f"{tour.pk}/data/train/{waypoint.title}/{image.image.name.split('/')[-1]}", image.image)
                        for image in waypoint.images.filter(type_of_images=TypeOfImage.DEFAULT.value)[train:]:
                            storage.save(f"{tour.pk}/data/test/{waypoint.title}/{image.image.name.split('/')[-1]}", image.image)
                        
                    lat = float(waypoint.coordinates.split(",")[0].strip()) if waypoint.coordinates else None
                    lon = float(waypoint.coordinates.split(",")[1].strip()) if waypoint.coordinates else None
                    if lat is not None and lon is not None:
                        gps_info = {
                            "name": waypoint.title,
                            "lat": lat,
                            "lon": lon,
                            "radius_m": 65
                        }
                        waypoints_gps.append(gps_info)
                            
            waypoints = tour.waypoints.filter(is_preliminary_info=False)
            for waypoint in waypoints:
                images = waypoint.images.filter(type_of_images=TypeOfImage.DEFAULT.value)
                num_img = len(images)
                if num_img < 5:
                    for i, image in enumerate(images):
                        storage.save(f"{tour.pk}/data/train/{waypoint.title}/{image.image.name.split("/")[-1]}", image.image)
                        if i == 1:
                            storage.save(f"{tour.pk}/data/test/{waypoint.title}/{image.image.name.split("/")[-1]}", image.image)
                else:
                    train = int(num_img * 0.8)
                    test = num_img - train
                    for image in images[:train]:
                        storage.save(f"{tour.pk}/data/train/{waypoint.title}/{image.image.name.split("/")[-1]}", image.image)
                    for image in images[train:]:
                        storage.save(f"{tour.pk}/data/test/{waypoint.title}/{image.image.name.split("/")[-1]}", image.image)
                        
                #GPS COORD
                if waypoint.coordinates is not None:
                    coord = waypoint.coordinates
                    lat = float(coord.split(",")[0].strip())
                    lon = float(coord.split(",")[1].strip())
                    gps_info = {
                        "name": waypoint.title,
                        "lat": lat,
                        "lon": lon,
                        "radius_m": 65
                    }
                    waypoints_gps.append(gps_info)
                        
        except Exception as e:
            print(f"Errore nella creazione delle cartelle per il train e test: {e}")
        try:
            payload = {
                "poi_name": tour.title,
                "poi_id": str(tour.id),
                "data_url": f"{tour_id}",
                "waypoint_gps": {
                    "waypoints": waypoints_gps
                }
            }

            try:
                url = os.getenv("TRAIN_ENDPOINT")
                headers = {"Content-type": "application/json"}
                response = requests.post(url, headers=headers, json=payload, verify=False)
            except Exception as e:  
                print(f"Errore nella chiamata API: {e}")
                
            print("Response status code:", response.status_code)
            print(response)
            
            if response.status_code == 200:
                tour.status = Status.BUILDING
                tour.build_started_at = timezone.now()
                tour.save()
                send_mail(
                    'Build in corso',
                    f"Tour {tour.title} in fase di build.",
                    os.environ.get('EMAIL_HOST_USER'),
                    [tour.user.email],
                    fail_silently=False,
                )
                return f"Tour {tour} in building"
            else:
                status = Status.FAILED
                tour.status = status
                tour.save()
                send_mail(
                    'Build Fallita',
                    f"Tour: {tour.title} fallita. Errore interno del server",
                    os.environ.get('EMAIL_HOST_USER'),
                    [tour.user.email],
                    fail_silently=False,
                )
                if lock.locked():
                    print("Rilascio il lock...")
                    lock.release()
                return f"Build failed for Tour {tour}"  

        except Exception as e:
            print(f"Errore nella chiamata API: {e}")
            if response is not None and response.status_code != 200:
                status = Status.FAILED
                tour.status = status
                tour.save()
                send_mail(
                    'Build Fallita',
                    f"Tour: {tour.title} fallita. Errore interno del server",
                    os.environ.get('EMAIL_HOST_USER'),
                    [tour.user.email],
                    fail_silently=False,
                )
            return str(e)
        finally:
            pass
            # if lock.locked():
            #     print("Rilascio il lock...")
            #     lock.release()

    except Tour.DoesNotExist:
        return f"Tour {tour} does not exist."

    except Exception as e:
        print(f"Errore generale: {e}")
        if response is not None and response.status_code != 200:
            status = Status.FAILED
            tour.status = status
            tour.save()
            send_mail(
                'Build Fallita',
                f"Tour: {tour.title} fallita. Errore interno del server",
                os.environ.get('EMAIL_HOST_USER'),
                [tour.user.email],
                fail_silently=False,
            )
        return str(e)

@shared_task(queue='api_tasks')
def fail_stuck_builds():
    try:
        redis_client = redis.StrictRedis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
        build_lock = Lock(redis_client, "build_lock")
    except Exception as e:
        print(f"Errore nell'acquisizione del lock: {e}")
            
    cromo_poi = None
    try:
        # timeout_minutes = 10 #18 * 60 # 18 hours
        # threshold = timezone.now() - timedelta(minutes=1)
        try:
            configured_timeout = int(os.getenv("BUILD_TIMEOUT_MINUTES", 30))
        except ValueError:
            configured_timeout = 30
        
        timeout_minutes = max(1, min(configured_timeout, 45))
        threshold = timezone.now() - timedelta(minutes=timeout_minutes)

        cromo_poi = Tour.objects.filter(status=Status.BUILDING, build_started_at__lt=threshold).first()
    except Tour.DoesNotExist:
        print("Tour does not exist")
    except Exception as e:
        print(f"Errore: {e}")
        
    if cromo_poi is None:
        return
    try:
        cromo_poi.status = Status.FAILED
        cromo_poi.save()
        send_mail(
            'Build Fallita',
            f"Tour: {cromo_poi.title} è fallita automaticamente per superamento del tempo massimo di build.",
            os.environ.get('EMAIL_HOST_USER'),
            [cromo_poi.user.email],
            fail_silently=False,
        )
    except Exception as e:
        print(f"Errore nell'acquisizione del lock: {e}")
    
    try:
        redis_client.delete("build_lock")
    except Exception as e:
        print(f"Errore nell'acquisizione del lock: {e}")

@shared_task(queue='api_tasks')
def remove_append_user():
    try:
        one_minute_ago = timezone.now() - timedelta(minutes=30)
        User = get_user_model()
        users = User.objects.filter(date_joined__lt=one_minute_ago, is_active=False)
        count, _ = users.delete()
        print(f"{count} utenti eliminati", flush=True)
    except Exception as e:
        print(f"Errore nella cancellazione degli utenti: {e}", flush=True)

@shared_task(queue='api_tasks')
def remove_sub_tours():
    difference = timezone.now() - timedelta(hours=5)
    tours = Tour.objects.filter(is_subtour=True, parent_tours__isnull=True, created_at__lt=difference)
    for tour in tours:
        tour.delete()
        
@shared_task
def clear_ai_inference_cache():
    url = os.getenv("INFERENCE_CACHE_CLEAR_ENDPOINT")
    
    if not url:
        print("INFERENCE_CACHE_CLEAR_ENDPOINT non è configurato.")
        return "INFERENCE_CACHE_CLEAR_ENDPOINT non configurato"
    
    headers = {}
    
    try:
        response = requests.post(url, timeout=30)
        print(f"Cache clear response: {response.status_code} - {response.text}")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error clearing AI inference cache: {e}", flush=True)
        raise
    
@shared_task(queue='api_tasks')
def generate_offline_bundle(tour_id):
    from xr_tour_guide_core.services.offline_bundle_service import OfflineBundleService
    from xr_tour_guide_core.models import Tour, Status

    try:
        service = OfflineBundleService()
        result = service.build_offline_bundle(tour_id)
        try:
            tour = Tour.objects.get(pk=tour_id)
            if tour.status == Status.ENQUEUED:
                tour.status = Status.BUILT
                tour.save(update_fields=["status"])
        except Tour.DoesNotExist:
            pass
        
        print(f"Offline bundle generated: {result}")
        return result
    except Exception as e:
        try:
            tour = Tour.objects.get(pk=tour_id)
            if tour.status == Status.ENQUEUED:
                tour.status = Status.FAILED
                tour.save(update_fields=["status"])
        except Exception:
            pass
        
        print(f"Offline bundle generation failed for tour {tour_id}: {e}")
        return {"ok": False, "error": str(e)}