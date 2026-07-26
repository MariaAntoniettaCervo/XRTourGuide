import hashlib
import json
import os
import time
import uuid

import requests
from celery.result import AsyncResult
from django.contrib.auth.decorators import login_required
from django.core.cache import caches
from django.core.files.base import ContentFile
from django.http import HttpResponse, JsonResponse
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
def optimize_markdown_start(request):
    data = _read_json(request)
    text = (data.get("text") or "").strip()
    tone = data.get("tone") or "professional"
    model = data.get("model") or "llama3.1:8b"
    if not text:
        return JsonResponse({"error": "text mancante"}, status=400)

    job_id = str(uuid.uuid4())
    async_result = optimize_text_task.apply_async(
        args=[job_id, "markdown", {"text": text, "tone": tone, "model": model}], queue='api_tasks'
    )
    # Serve per poter annullare il task se la pagina viene abbandonata prima
    # che risponda (vedi optimize_text_cancel).
    caches["redis"].set(f"ai_job_task_id:{job_id}", async_result.id, timeout=600)  # stesso TTL di ai_job:{job_id} in tasks.py
    return JsonResponse({"status": "processing", "job_id": job_id})


@login_required
@require_POST
def optimize_title_start(request):
    data = _read_json(request)
    original_title = (data.get("original_title") or "").strip()
    model = data.get("model") or "llama3.1:8b"
    if not original_title:
        return JsonResponse({"error": "original_title mancante"}, status=400)

    job_id = str(uuid.uuid4())
    async_result = optimize_text_task.apply_async(
        args=[job_id, "title", {"original_title": original_title, "model": model}], queue='api_tasks'
    )
    caches["redis"].set(f"ai_job_task_id:{job_id}", async_result.id, timeout=600)
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
    async_result = optimize_text_task.apply_async(
        args=[job_id, "description", {"original_text": original_text, "model": model}], queue='api_tasks'
    )
    caches["redis"].set(f"ai_job_task_id:{job_id}", async_result.id, timeout=600)
    return JsonResponse({"status": "processing", "job_id": job_id})


@login_required
@require_POST
def optimize_text_cancel(request):
    """
    Annulla un task di ottimizzazione testo (titolo/descrizione/markdown)
    ancora in corso — tipicamente chiamato quando l'utente abbandona la
    pagina prima che l'IA abbia risposto, per non far girare a vuoto un
    calcolo il cui risultato non verrà mai visto (il testo non salvato non
    torna comunque, indipendentemente da questo annullamento).

    Non tocca in nessun modo il contenuto dei campi: agisce solo sul task
    Celery/Ollama in background.
    """
    data = _read_json(request)
    job_id = data.get("job_id")
    if not job_id:
        return JsonResponse({"error": "job_id obbligatorio"}, status=400)

    task_id = caches["redis"].get(f"ai_job_task_id:{job_id}")
    if task_id:
        try:
            AsyncResult(task_id).revoke(terminate=True)
        except Exception:
            pass  # non critico: nel peggiore dei casi il task finisce comunque, inutilizzato

    caches["redis"].delete(f"ai_job_task_id:{job_id}")
    caches["redis"].delete(f"ai_job:{job_id}")

    return JsonResponse({"ok": True})


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
def waypoint_audio_player(request):
    """
    Restituisce solo l'HTML aggiornato del player audio di un waypoint (senza
    ricaricare l'intera pagina). Usata dal JS per sostituire in-place il
    contenuto del contenitore #audio-player-container-{location}-{waypoint_id}
    quando una conferma arriva dopo che la pagina è già stata caricata.
    """
    waypoint_id = request.GET.get("waypoint_id")
    location = request.GET.get("location") or "main"
    if not waypoint_id:
        return JsonResponse({"error": "waypoint_id obbligatorio"}, status=400)

    waypoint, error = _get_waypoint_or_error(request, waypoint_id)
    if error:
        return error

    from ..admin.audio_player_widget import render_audio_player
    html = str(render_audio_player(waypoint, location=location))
    return JsonResponse({"html": html})


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

    # Segna esplicitamente "generazione in corso per QUESTO waypoint": senza
    # questo, il polling vedrebbe subito "ready" se esisteva già un audio
    # precedente (es. generato con un altro motore), scambiandolo per quello
    # nuovo appena richiesto.
    caches["redis"].set(f"audio_pending:{waypoint_id}", True, timeout=900)

    # Ricordiamo l'hash di QUESTO testo, non ancora confermato: diventerà
    # "confermato" solo quando arriverà davvero il callback di successo
    # (vedi generate_audio_callback). Serve per il confronto "testo cambiato
    # dopo l'ultima generazione" nel player audio dell'admin.
    text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
    caches["redis"].set(f"audio_pending_hash:{waypoint_id}", text_hash, timeout=900)

    generate_waypoint_audio.apply_async(args=[waypoint.pk, text, tts_engine], queue='api_tasks')

    return JsonResponse({"status": "processing", "waypoint_id": waypoint_id})


@login_required
def generate_audio_status(request):
    """
    Polling: durante la generazione -> "processing". Appena l'audio è pronto
    -> "preview_ready" (non ancora salvato su audio_item: l'utente lo ascolta
    e decide se scartarlo con /discard, oppure lo lascia lì finché non salva
    il form intero, che lo conferma automaticamente). "ready" resta per
    compatibilità nei rari casi in cui l'anteprima sia già stata confermata
    (dalla rete di sicurezza del signal) prima che il polling arrivasse qui.
    """
    waypoint_id = request.GET.get("waypoint_id")
    if not waypoint_id:
        return JsonResponse({"error": "waypoint_id obbligatorio"}, status=400)

    waypoint, error = _get_waypoint_or_error(request, waypoint_id)
    if error:
        return error

    if caches["redis"].get(f"audio_pending:{waypoint_id}"):
        return JsonResponse({"status": "processing"})

    if caches["redis"].get(f"audio_preview:{waypoint_id}") is not None:
        return JsonResponse({"status": "preview_ready"})

    if waypoint.audio_item and waypoint.audio_item.name:
        return JsonResponse({"status": "ready"})

    return JsonResponse({"status": "processing"})


@csrf_exempt
@require_POST
def generate_audio_callback(request):
    """
    Chiamato dal modulo AI (server-to-server, rete Docker interna) quando l'audio
    è pronto. Non lo scriviamo mai subito su audio_item: lo mettiamo sempre in
    anteprima (cache Redis, 30 minuti). L'utente deve poterlo sempre ascoltare
    prima che diventi definitivo — nessuna conferma automatica silenziosa qui,
    nemmeno se il testo combacia già con quello salvato. Il salvataggio vero
    avviene solo tramite il signal post_save di Waypoint (vedi
    signals_ai_backend.py, scatta quando l'utente preme "Salva"), o viene
    scartato esplicitamente con /discard.

    Se l'utente ricarica la pagina mentre la generazione è ancora in corso,
    è il JavaScript, al caricamento della pagina, a ricontrollare lo stato e
    a mostrare l'anteprima appena disponibile (vedi initWaypointTextButtons
    in ai_backend_buttons.js) — non una conferma automatica qui.
    """
    waypoint_id = request.POST.get("waypoint_id")
    audio_file = request.FILES.get("audio")

    if not waypoint_id or not audio_file:
        return JsonResponse({"error": "waypoint_id e audio sono obbligatori"}, status=400)

    try:
        Waypoint.objects.get(pk=waypoint_id)
    except Waypoint.DoesNotExist:
        return JsonResponse({"error": "Waypoint non trovato"}, status=404)

    audio_bytes = audio_file.read()
    caches["redis"].set(f"audio_preview:{waypoint_id}", audio_bytes, timeout=1800)  # 30 minuti

    # Il polling ora può smettere di dire "processing": c'è un'anteprima pronta.
    caches["redis"].delete(f"audio_pending:{waypoint_id}")

    return JsonResponse({"ok": True, "preview": True})


@login_required
def generate_audio_preview(request):
    """Serve i byte grezzi dell'anteprima in sospeso, per farla ascoltare prima di salvarla."""
    waypoint_id = request.GET.get("waypoint_id")
    if not waypoint_id:
        return JsonResponse({"error": "waypoint_id obbligatorio"}, status=400)

    waypoint, error = _get_waypoint_or_error(request, waypoint_id)
    if error:
        return error

    preview_bytes = caches["redis"].get(f"audio_preview:{waypoint_id}")
    if preview_bytes is None:
        return JsonResponse({"error": "Nessuna anteprima disponibile"}, status=404)

    return HttpResponse(preview_bytes, content_type="audio/mpeg")


def _commit_audio_preview(waypoint):
    """
    Rende definitiva l'anteprima in sospeso per un waypoint, se esiste.
    Chiamata dal signal post_save di Waypoint: è l'UNICO modo in cui un'anteprima
    diventa definitiva (nessun bottone "Salva" dedicato — solo il "Salva"
    generale del form, o lo scarto esplicito via /discard).

    Restituisce True se ha effettivamente confermato qualcosa, False se non
    c'era nessuna anteprima in sospeso (nessuna azione da fare).
    """
    cache = caches["redis"]
    preview_bytes = cache.get(f"audio_preview:{waypoint.pk}")
    if preview_bytes is None:
        return False

    # Cancelliamo il file precedente PRIMA di salvare quello nuovo: con
    # AWS_S3_FILE_OVERWRITE=False (impostazione già presente nel progetto),
    # Django non sovrascrive un file con lo stesso nome — gli appiccica un
    # suffisso casuale (es. "audio_ozL1LWh.mp3"), violando il vincolo del
    # tutor che vuole sempre e solo "audio.mp3". Cancellando prima, il nuovo
    # salvataggio non trova conflitti e mantiene il nome esatto.
    if waypoint.audio_item:
        waypoint.audio_item.delete(save=False)

    waypoint.audio_item = ContentFile(preview_bytes, name="audio.mp3")
    waypoint.save(update_fields=["audio_item"])

    pending_hash = cache.get(f"audio_pending_hash:{waypoint.pk}")
    if pending_hash:
        cache.set(f"audio_confirmed_hash:{waypoint.pk}", pending_hash, timeout=None)
        cache.delete(f"audio_pending_hash:{waypoint.pk}")

    cache.delete(f"audio_preview:{waypoint.pk}")
    cache.set(f"audio_version:{waypoint.pk}", str(time.time()), timeout=None)
    return True


@login_required
@require_POST
def generate_audio_discard(request):
    """Click esplicito 'Scarta': butta via l'anteprima, non tocca l'audio già salvato in precedenza."""
    data = _read_json(request)
    waypoint_id = data.get("waypoint_id")
    if not waypoint_id:
        return JsonResponse({"error": "waypoint_id obbligatorio"}, status=400)

    waypoint, error = _get_waypoint_or_error(request, waypoint_id)
    if error:
        return error

    caches["redis"].delete(f"audio_preview:{waypoint_id}")
    caches["redis"].delete(f"audio_pending_hash:{waypoint_id}")

    return JsonResponse({"ok": True})