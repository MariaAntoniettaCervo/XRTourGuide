import json
import os
import uuid

import requests
from django.contrib.auth.decorators import login_required
from django.core.cache import caches
from django.core.files.base import ContentFile
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from ..models import Waypoint
from xr_tour_guide.tasks import generate_waypoint_audio, optimize_text_task

AI_BACKEND_ENDPOINT = os.getenv("AI_BACKEND_ENDPOINT", "http://ai_backend:8000")


def _read_json(request):
    try:
        return json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


@login_required
@require_POST
def optimize_title_start(request):
    data = _read_json(request)
    original_title = (data.get("original_title") or "").strip()
    model = data.get("model") or "llama3.1:8b"
    if not original_title:
        return JsonResponse({"error": "original_title mancante"}, status=400)

    job_id = str(uuid.uuid4())
    optimize_text_task.apply_async(
        args=[job_id, "title", {"original_title": original_title, "model": model}], queue='api_tasks'
    )
    return JsonResponse({"status": "processing", "job_id": job_id})


@login_required
@require_POST
def optimize_description_start(request):
    data = _read_json(request)
    original_text = (data.get("original_text") or "").strip()
    model = data.get("model") or "llama3.1:8b"
    if not original_text:
        return JsonResponse({"error": "original_text mancante"}, status=400)

    job_id = str(uuid.uuid4())
    optimize_text_task.apply_async(
        args=[job_id, "description", {"original_text": original_text, "model": model}], queue='api_tasks'
    )
    return JsonResponse({"status": "processing", "job_id": job_id})


@login_required
def optimize_text_status(request):
    job_id = request.GET.get("job_id")
    if not job_id:
        return JsonResponse({"error": "job_id obbligatorio"}, status=400)

    cache = caches["redis"]
    result = cache.get(f"ai_job:{job_id}")

    if result is None:
        return JsonResponse({"status": "processing"})

    # Consumato: una volta letto dal browser, lo ripuliamo (evita riletture doppie)
    cache.delete(f"ai_job:{job_id}")
    return JsonResponse(result)


def _get_waypoint_or_error(request, waypoint_id):
    """Recupera il waypoint verificando i permessi. Restituisce (waypoint, None) o (None, JsonResponse)."""
    try:
        waypoint = Waypoint.objects.get(pk=waypoint_id)
    except Waypoint.DoesNotExist:
        return None, JsonResponse({"error": "Waypoint non trovato"}, status=404)

    if not request.user.is_superuser and waypoint.tour.user != request.user:
        return None, JsonResponse({"error": "Non autorizzato"}, status=403)

    return waypoint, None


@login_required
@require_POST
def generate_audio_start(request):
    """
    Accoda il task Celery e risponde subito, senza attendere.
    Stesso schema di build_tour_view -> call_api_and_save.apply_async(...).
    """
    data = _read_json(request)
    waypoint_id = data.get("waypoint_id")
    text = (data.get("text") or "").strip()
    tts_engine = data.get("tts_engine") or "coqui-xtts"

    if not waypoint_id or not text:
        return JsonResponse({"error": "waypoint_id e text sono obbligatori"}, status=400)

    waypoint, error = _get_waypoint_or_error(request, waypoint_id)
    if error:
        return error

    generate_waypoint_audio.apply_async(args=[waypoint.pk, text, tts_engine], queue='api_tasks')

    return JsonResponse({"status": "processing", "waypoint_id": waypoint_id})


@login_required
def generate_audio_status(request):
    """
    Polling leggero: controlla solo lo stato locale del waypoint.
    Non contatta mai il modulo AI: sarà lui a notificarci via callback.
    """
    waypoint_id = request.GET.get("waypoint_id")
    if not waypoint_id:
        return JsonResponse({"error": "waypoint_id obbligatorio"}, status=400)

    waypoint, error = _get_waypoint_or_error(request, waypoint_id)
    if error:
        return error

    if waypoint.audio_item and waypoint.audio_item.name:
        return JsonResponse({"status": "ready"})

    return JsonResponse({"status": "processing"})


@csrf_exempt
@require_POST
def generate_audio_callback(request):
    """
    Chiamato dal modulo AI (server-to-server, rete Docker interna) quando l'audio
    è pronto. Stesso ruolo di complete_build per la pipeline di training: qui
    niente permission_classes utente, ma nessun dato sensibile viene esposto
    in risposta (solo un ok/errore).

    Formato atteso: multipart/form-data con
      - waypoint_id (str)
      - audio (file)
    """
    waypoint_id = request.POST.get("waypoint_id")
    audio_file = request.FILES.get("audio")

    if not waypoint_id or not audio_file:
        return JsonResponse({"error": "waypoint_id e audio sono obbligatori"}, status=400)

    try:
        waypoint = Waypoint.objects.get(pk=waypoint_id)
    except Waypoint.DoesNotExist:
        return JsonResponse({"error": "Waypoint non trovato"}, status=404)

    waypoint.audio_item = ContentFile(audio_file.read(), name="audio.mp3")
    waypoint.save(update_fields=["audio_item"])

    return JsonResponse({"ok": True})