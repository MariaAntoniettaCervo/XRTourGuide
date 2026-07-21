from minio import Minio
from minio.error import S3Error
import json
import io
import os

from app.app_config import global_settings

# --- MINIO CLIENT INIT ---
# Inizializziamo il client immediatamente all'importazione del modulo.
# Questo oggetto sarà riutilizzato per tutte le chiamate (Singleton-like behavior).
client = Minio(
    global_settings.minio_endpoint,
    access_key=global_settings.minio_access_key,
    secret_key=global_settings.minio_secret_key,
    secure=global_settings.minio_secure
)

def init_storage():
    """
    Configura l'ambiente di storage all'avvio dell'applicazione.
    
    Operazioni svolte:
    1. Verifica esistenza Bucket: Se manca, lo crea.
    2. Configurazione Permessi (CORS/Policy): Applica una policy 'Public Read'.
       Questo è CRITICO: senza questa policy, il frontend (React/App) riceverebbe 
       un errore 403 Forbidden provando a riprodurre gli MP3.

    La funzione è idempotente: non fa danni se richiamata più volte.
    """
    bucket_name = global_settings.minio_bucket
    try:
        # 1. Crea il bucket se non esiste
        if not client.bucket_exists(bucket_name):
            print(f"STORAGE: Creazione bucket '{bucket_name}'...")
            client.make_bucket(bucket_name)
        else:
            print(f"STORAGE: Bucket '{bucket_name}' trovato.")

        # 2. Definizione Policy JSON
        # Definisce che CHIUNQUE (Principal: *) può LEGGERE (s3:GetObject)
        # qualsiasi file all'interno del bucket.
        
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "PublicRead",
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{bucket_name}/*"]
                }
            ]
        }
        client.set_bucket_policy(bucket_name, json.dumps(policy))
        print(f"STORAGE: Policy 'Public Read' applicata a '{bucket_name}'.")
            
    except Exception as e:
        # Non blocchiamo l'app, ma logghiamo l'errore (potrebbe essere MinIO offline)
        print(f"ATTENZIONE: Errore configurazione MinIO: {e}")

def check_file_exists(object_name: str) -> bool:
    """
    Verifica rapida se un file esiste senza scaricarlo.
    Utilizza 'stat_object' che richiede solo i metadati (molto veloce).
    """
    try:
        client.stat_object(global_settings.minio_bucket, object_name)
        return True
    except S3Error:
        return False

def get_file_url(object_name: str) -> str:
    """
    Costruisce l'URL pubblico per accedere al file.
    Non genera URL presigned (a scadenza), ma URL statici diretti
    grazie alla policy Public Read impostata in init_storage().
    """
    protocol = "https" if global_settings.minio_secure else "http"
    return f"{protocol}://{global_settings.minio_endpoint}/{global_settings.minio_bucket}/{object_name}"

def upload_file(file_path: str, object_name: str):
    """
    Carica un file locale su MinIO.
    
    Args:
        file_path: Percorso del file su disco locale (es. /tmp/audio.mp3).
        object_name: Nome finale del file nel bucket (es. audio/123.mp3).
    
    Note:
        Imposta automaticamente il Content-Type. Questo assicura che il browser
        riproduca il file invece di forzarne il download.
    """
    content_type = "audio/mpeg" if file_path.endswith(".mp3") else "audio/wav"
    try:
        client.fput_object(
            global_settings.minio_bucket, 
            object_name, 
            file_path, 
            content_type=content_type
        )
        print(f"MinIO: Upload completato -> {object_name}")
    except S3Error as e:
        print(f"MinIO Upload Error: {e}")
        raise e

def delete_file(object_name: str):
    """Rimuove un oggetto dal bucket (utile per cleanup o rigenerazione)."""
    try:
        client.remove_object(global_settings.minio_bucket, object_name)
        print(f"MinIO: Cancellato {object_name}")
    except S3Error as e:
        print(f"MinIO Delete Error ({object_name}): {e}")    

def save_json_to_minio(data: dict, object_name: str):
    """
    Salva un dizionario Python direttamente come file JSON su MinIO.
    
    Tecnica: In-Memory Stream.
    Non scriviamo il JSON su disco locale per poi caricarlo. Usiamo io.BytesIO
    per creare un 'file virtuale' in RAM e inviarlo direttamente alla rete.
    """
    
    try:
        json_bytes = json.dumps(data, ensure_ascii=False).encode('utf-8')
        data_stream = io.BytesIO(json_bytes)
        
        client.put_object(
            global_settings.minio_bucket,
            object_name,
            data_stream,
            length=len(json_bytes),
            content_type="application/json"
        )
        print(f"MinIO: Salvato JSON in memoria -> {object_name}")
        
    except Exception as e:
        print(f"Errore salvataggio JSON MinIO: {e}")

def get_json_from_minio(object_name: str) -> dict:
    """
    Scarica e parsa un file JSON da MinIO.
    Gestisce correttamente la chiusura della connessione stream.
    """
    response = None
    try:
        response = client.get_object(global_settings.minio_bucket, object_name)
        content = response.read()
        return json.loads(content)
    except Exception as e:
        print(f"MinIO: Impossibile leggere JSON {object_name}: {e}")
        return {}
    finally:
        # È fondamentale rilasciare la connessione al pool http
        if response:
            response.close()
            response.release_conn()