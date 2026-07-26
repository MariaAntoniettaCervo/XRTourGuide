from fastapi import FastAPI, HTTPException, BackgroundTasks
from contextlib import asynccontextmanager
import os
import asyncio
import hashlib
import uvicorn
import requests

# Schemas
from app.utils.text_processing import smart_chunking
from app.schemas import (
    TitleRequest, TitleResponse, 
    DescriptionRequest, DescriptionResponse,
    AudioGenerationRequest, AudioGenerationResponse,
    MarkdownFixRequest, MarkdownFixResponse,
    ComputeChunksRequest
)

# Factory
from app.tts.factory import TTSFactory

# Services
from app.llm.services.optimize_title import generate_optimized_title
from app.llm.services.optimize_description import generate_optimized_description
from app.llm.services.optimize_markdown import fix_markdown

# Storage
from app.storage import check_file_exists, get_file_url, upload_file, delete_file, save_json_to_minio, get_json_from_minio, init_storage,  get_file_bytes

# --- CONFIGURAZIONE DOCUMENTAZIONE (TAGS) ---
tags_metadata = [
    {
        "name": "Audio Generation",
        "description": "Gestione del motore TTS (Text-to-Speech) e creazione file audio.",
    },
    {
        "name": "AI Content Optimization",
        "description": "Servizi LLM per migliorare titoli, descrizioni e formattazione.",
    },
    {
        "name": "Health Check",
        "description": "Verifica stato del servizio.",
    },
]

# --- GLOBAL LOCK PER TTS ---
tts_lock = asyncio.Lock()

# --- LIFESPAN ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Avvio Backend XRTourGuide...")
    init_storage()
    yield
    print("Shutdown Backend.")

# --- APP INIT ---
app = FastAPI(
    title="XRTourGuide AI Backend",
    description="""
    Backend AI per la generazione di audioguide turistiche immersive.
    
    Moduli Principali
        TTS Engine: Genera file MP3 usando modelli neurali (Piper/Coqui). Include gestione della coda e caching.
        LLM Optimization: Migliora i testi e i titoli per renderli più accattivanti per i turisti.
        Storage: Integrazione automatica con MinIO (S3 compatible) per l'hosting dei file.
    """,
    version="2.1.0",
    openapi_tags=tags_metadata,
    lifespan=lifespan
)

# --- WORKER TASK (Logica interna, non esposta) ---
async def background_audio_task(
    text_to_read: str,
    object_name: str,
    local_temp: str,
    engine_name: str,
    waypoint_id: str | None = None,
    callback_url: str | None = None,
):
    json_object_name = f"{hashlib.md5(text_to_read.encode('utf-8')).hexdigest()}.json"
    error_object_name = object_name.replace(".mp3", ".err")
 
    async with tts_lock:
        try:
            print(f"WORKER: Richiesto engine {engine_name}")
            tts_engine = TTSFactory.get_engine(engine_name)
 
            loaded_chunks = []
            if check_file_exists(json_object_name):
                print(f"WORKER: Trovato copione JSON {json_object_name}")
                data = get_json_from_minio(json_object_name)
                loaded_chunks = data.get("tts_chunks", [])
 
            print(f"WORKER: Avvio Generazione...")
 
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                None,
                lambda: tts_engine.generate_audio(
                    text=text_to_read,
                    output_filename=local_temp,
                    chunks=loaded_chunks
                )
            )
 
            if success and os.path.exists(local_temp):
                upload_file(local_temp, object_name)
                try: delete_file(error_object_name)
                except: pass
 
                # --- NOTIFICA CALLBACK (integrazione XRTourGuide) ---
                if waypoint_id and callback_url:
                    try:
                        with open(local_temp, "rb") as audio_file:
                            requests.post(
                                callback_url,
                                data={"waypoint_id": waypoint_id},
                                files={"audio": ("audio.mp3", audio_file, "audio/mpeg")},
                                timeout=30,
                            )
                        print(f"WORKER: Callback inviato a Django per waypoint {waypoint_id}")
                    except Exception as callback_error:
                        print(f"WORKER: Errore invio callback a Django: {callback_error}")
 
                os.remove(local_temp)
            else:
                raise Exception("TTS Engine returned False.")
 
        except Exception as e:
            print(f"WORKER ERROR: {e}")
            local_err = local_temp.replace(".mp3", ".err")
            with open(local_err, "w") as f:
                f.write(str(e))
            upload_file(local_err, error_object_name)
 
            if os.path.exists(local_temp): os.remove(local_temp)
            if os.path.exists(local_err): os.remove(local_err)

# --- ENDPOINTS ---

@app.get("/", tags=["Health Check"])
def root():
    """
    Endpoint di controllo stato.
    Usa questo per verificare se il container Docker è attivo.
    """
    return {
        "status": "online", 
        "service": "XRTourGuide AI Backend", 
        "version": "2.1 (Multi-Model Support)"
    }

@app.post(
    "/generate-audio",
    response_model=AudioGenerationResponse,
    status_code=202,
    tags=["Audio Generation"],
    summary="Genera Audioguida (TTS)",
    description="""
    Avvia un task asincrono per convertire il testo in audio MP3.

    - Se l'audio esiste già (cache), restituisce 200 OK.
    - Se l'audio è nuovo, avvia il worker in background e restituisce 202 Accepted.
    """,
    responses={
        200: {"description": "Audio già disponibile in cache"},
        202: {"description": "Elaborazione avviata in background"},
        400: {"description": "Testo vuoto o parametri non validi"}
    }
)
async def generate_audio(request: AudioGenerationRequest, background_tasks: BackgroundTasks):
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Testo vuoto")

    combo_string = f"{request.text}_{request.tts_engine.value}"
    text_hash = hashlib.md5(combo_string.encode('utf-8')).hexdigest()

    object_name = f"{text_hash}.mp3"
    error_object_name = f"{text_hash}.err"
    audio_url = get_file_url(object_name)

    if check_file_exists(object_name):
        # --- CACHE HIT ---
        # L'audio esiste già, ma senza notifica il chiamante (Django, nella
        # nostra integrazione) resterebbe in attesa per sempre: il callback
        # normalmente parte solo da background_audio_task, che qui non viene
        # mai eseguito perché non c'è nulla da generare. Lo inviamo quindi
        # subito qui, riusando il file già presente in cache.
        if request.waypoint_id and request.callback_url:
            try:
                audio_bytes = get_file_bytes(object_name)
                requests.post(
                    request.callback_url,
                    data={"waypoint_id": request.waypoint_id},
                    files={"audio": ("audio.mp3", audio_bytes, "audio/mpeg")},
                    timeout=30,
                )
                print(f"CACHE HIT: Callback inviato a Django per waypoint {request.waypoint_id} (audio già esistente)")
            except Exception as callback_error:
                print(f"CACHE HIT: Errore invio callback: {callback_error}")

        return AudioGenerationResponse(
            audio_url=audio_url,
            status="ready",
            message=f"Audio già pronto (generato con {request.tts_engine.value})."
        )

    if check_file_exists(error_object_name):
        if not request.retry:
            return AudioGenerationResponse(
                audio_url="",
                status="error",
                message="Errore precedente rilevato. Invia 'retry': true per riprovare."
            )
        else:
            try: delete_file(error_object_name)
            except: pass

    local_temp = f"temp_{text_hash}.mp3"
    print(f"NEW REQUEST: Audio '{request.tts_engine.value}' per '{request.text[:15]}...'")

    background_tasks.add_task(
        background_audio_task,
        request.text,
        object_name,
        local_temp,
        request.tts_engine.value,
        request.waypoint_id,
        request.callback_url,
    )

    return AudioGenerationResponse(
        audio_url=audio_url,
        status="processing",
        message="Elaborazione in corso..."
    )

@app.post(
    "/optimize/title", 
    response_model=TitleResponse,
    tags=["AI Content Optimization"],
    summary="Ottimizzazione Titoli",
    description="Analizza un titolo grezzo e restituisce 3 varianti (breve, evocativa, ingaggiante) ottimizzate per il turismo."
)
async def optimize_title_endpoint(request: TitleRequest):
    if not request.original_title:
        raise HTTPException(status_code=400, detail="Il titolo non può essere vuoto")
        
    result = generate_optimized_title(request.original_title, model_name=request.model.value)
    return result


@app.post(
    "/optimize/description", 
    response_model=DescriptionResponse,
    tags=["AI Content Optimization"],
    summary="Ottimizzazione & Scripting Descrizione",
    description="""
    Riscrive una descrizione turistica per renderla più adatta all'ascolto (TTS Friendly).
    
    Side Effect:
    Salva automaticamente su MinIO un file JSON contenente i 'chunks' (segmenti di testo) 
    che verranno usati dal motore audio per gestire le pause.
    """
)
async def optimize_description_endpoint(request: DescriptionRequest):
    if not request.original_text:
        raise HTTPException(status_code=400, detail="Il testo non può essere vuoto")

    result = generate_optimized_description(request.original_text, model_name=request.model.value)
    return result

@app.post(
    "/compute-chunks",
    tags=["Audio Generation"],
    summary="Calcola e persisti i chunks TTS per un testo definitivo",
    description="""
    Calcola i chunks (smart_chunking) per il testo esatto
    fornito e li salva su MinIO, indicizzati dall'hash di quel testo.
 
    Va chiamato ogni volta che una descrizione (Tour o Waypoint) viene salvata
    davvero, così un futuro /generate-audio su quello stesso testo troverà
    chunks già pronti invece di calcolarli al volo.
    """
)
async def compute_chunks_endpoint(request: ComputeChunksRequest):
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Il testo non può essere vuoto")
 
    chunks = smart_chunking(request.text)
 
    text_hash = hashlib.md5(request.text.encode('utf-8')).hexdigest()
    json_object_name = f"{text_hash}.json"
 
    payload_to_save = {
        "full_text_optimized": request.text,
        "tts_chunks": chunks
    }
    save_json_to_minio(payload_to_save, json_object_name)
 
    return {"ok": True, "object_name": json_object_name}


@app.post(
    "/optimize-markdown", 
    response_model=MarkdownFixResponse,
    tags=["AI Content Optimization"],
    summary="Fix Markdown",
    description="Corregge la formattazione Markdown di un testo, rimuovendo artefatti indesiderati."
)
async def fix_markdown_endpoint(request: MarkdownFixRequest):
    return fix_markdown(request.text, model_name=request.model.value)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)