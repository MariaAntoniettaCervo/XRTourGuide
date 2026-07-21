from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum

# --- ENUMS (Scelte Predefinite) ---
# Menu di scelta per il modello di Intelligenza Artificiale (Testo).

class LLMModelEnum(str, Enum):
    """
    Menu di scelta per il modello di Intelligenza Artificiale (Testo).
    """
    # Opzione Veloce / Balanced 
    QWEN_7B = "qwen2.5:7b"
    # Opzione Qualità / Più Creativa (Default)
    LLAMA_8B = "llama3.1:8b"

class TTSModelEnum(str, Enum):
    """
    Menu di scelta per il motore di Sintesi Vocale (Audio).
    """
    # Opzione Veloce (CPU friendly - Voce meno naturale ma istantaneo)
    FAST_CPU = "piper" 
    # Opzione Qualità (GPU required - Realistico ma lento)
    QUALITY_GPU = "coqui-xtts"

# --- TITOLI (Optimization) ---

class TitleRequest(BaseModel):
    """
    Payload per la richiesta di ottimizzazione titoli.
    """
    original_title: str = Field(
        ..., 
        min_length=3, 
        max_length=100, 
        example="Il Colosseo Romano",
        description="Il titolo originale grezzo da migliorare."
    )
    model: LLMModelEnum = Field(
        default=LLMModelEnum.LLAMA_8B, 
        description="Scegli il modello AI da usare. Qwen è più veloce, Llama più creativo."
    )
    
class TitleResponse(BaseModel):
    """
    Struttura della risposta per i titoli.
    """
    original: str
    options: List[str] = Field(..., description="Lista di 3 varianti generate (Corto, Evocativo, Domanda).")
    best_option: str = Field(..., description="La variante raccomandata dall'AI.")
    model_used: str = Field(..., description="Il nome tecnico del modello che ha eseguito il task.")
    success: bool = Field(..., description="Indica se l'AI ha completato il task o se è andata in fallback.")
    error_message: Optional[str] = None
# --- DESCRIZIONI (Scripting) ---

class DescriptionRequest(BaseModel):
    """
    Payload per trasformare un testo scritto in uno script audio.
    """
    original_text: str = Field(
        ..., 
        min_length=10, 
        example="Questa statua risale al 1500 ed è stata scolpita da...",
        description="Il testo turistico originale."
    )
    target_lang: str = Field("it", description="Lingua di destinazione (attualmente supportato solo 'it').")
    
    model: LLMModelEnum = Field(
        default=LLMModelEnum.LLAMA_8B, 
        description="Modello LLM per la riscrittura."
    )

class DescriptionResponse(BaseModel):
    """
    Risultato dell'ottimizzazione descrizione.
    """
    full_text_optimized: str = Field(..., description="Il testo riscritto per essere letto ad alta voce (senza date complesse, ecc).")
    model_used: str
    success: bool = Field(..., description="Indica se l'AI ha completato il task o se è andata in fallback.")
    error_message: Optional[str] = None

class ComputeChunksRequest(BaseModel):
    """
    Richiesta di calcolo e persistenza chunks per un testo definitivo (già salvato).
    """
    text: str = Field(..., description="Il testo finale, esattamente come verrà convertito in audio.")

# --- FIX MARKDOWN ---

class MarkdownFixRequest(BaseModel):
    """
    Richiesta di correzione bozze e formattazione.
    """
    text: str = Field(..., description="Testo con potenziali errori di formattazione o grammatica.")
    tone: str = Field("professional", description="Tono di voce desiderato (es. 'friendly', 'academic').") 
    model: LLMModelEnum = Field(default=LLMModelEnum.LLAMA_8B)

class MarkdownFixResponse(BaseModel):
    """
    Risultato della correzione.
    """
    original_text: str
    fixed_text: str = Field(..., description="Il testo corretto e pulito.")
    success: bool = Field(..., description="Indica se l'AI ha completato il task o se è andata in fallback.")
    error_message: Optional[str] = None   

# --- AUDIO GENERATION ---

class AudioGenerationRequest(BaseModel):
    """
    Richiesta per generare il file MP3.
    """
    text: str = Field(..., example="Ciao, benvenuti al tour!")
    retry: bool = Field(False, description="Se True, forza la rigenerazione ignorando la cache.")
    
    # Scelta del motore Audio
    tts_engine: TTSModelEnum = Field(
        default=TTSModelEnum.QUALITY_GPU,
        description="Scegli 'piper' per velocità/CPU o 'coqui-xtts' per qualità/GPU."
    )

class AudioGenerationResponse(BaseModel):
    """
    Risposta asincrona per l'audio.
    """
    audio_url: str = Field(..., description="URL pubblico (MinIO) dove scaricare il file mp3.")
    status: str = Field(..., description="Stato attuale: 'processing', 'ready', 'error'.")
    message: Optional[str] = None