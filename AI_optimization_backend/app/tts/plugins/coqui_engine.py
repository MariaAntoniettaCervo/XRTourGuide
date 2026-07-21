import os
import torch
import torchaudio
import torchaudio.transforms as T
import gc 
from TTS.api import TTS
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts

from app.interfaces.tts_interface import TTSInterface
from app.tts.text_normalizer import TextNormalizer
from app.utils.audio_converter import AudioConverter
from app.app_config import global_settings
from app.utils.text_processing import smart_chunking

class CoquiTTS(TTSInterface):
    """
    Implementazione del motore Coqui XTTS v2 (High-End Neural TTS).

    Questa classe gestisce la generazione di voci neurali estremamente realistiche
    con supporto per il "Voice Cloning" (tramite file di riferimento).
    
    Architecture Highlights:
    - **Lazy Loading:** Il modello viene caricato in VRAM solo al momento della richiesta e scaricato subito dopo.
    - **Tensor Stitching:** Genera audio per frasi separate (chunks) e le unisce a livello di tensori PyTorch prima della conversione in file, garantendo transizioni fluide.
    - **DSP Pipeline:** Applica post-processing (Pitch Shift, Resampling) per migliorare la qualità audio finale.

    Attributes:
        GEN_SPEED (float): Velocità di lettura (1.1 = +10% velocità).
        PITCH_STEPS (float): Modifica il tono (-0.5 = voce leggermente più profonda/calda).
        SENTENCE_PAUSE_S (float): Secondi di silenzio inseriti tra una frase e l'altra.
    """

    # --- Hyperparameters (Voice Tuning) ---
    GEN_SPEED = 1.1        
    PITCH_STEPS = -0.5     
    GPT_COND_LEN = 6       # Lunghezza audio di riferimento per il condizionamento
    TEMP = 0.2             # Creatività (bassa = più stabile)
    REP_PENALTY = 5.0      # Penalità per evitare balbettii
    TOP_K = 60
    TOP_P = 0.8
    
    SENTENCE_PAUSE_S = 0.4 

    def __init__(self):
        """Inizializza il wrapper, ma NON carica ancora il modello (Lazy Init)."""
        print("Inizializzazione Plugin Coqui XTTS (Lazy Mode)...")
        self.normalizer = TextNormalizer()
        self.model = None
        self.config = None

    def _load_model(self):
        """
        Carica il modello XTTS v2 in memoria (RAM o VRAM).
        Se il modello non esiste localmente, lo scarica automaticamente.
        """
        if self.model is not None: return

        print("Caricamento XTTS v2 in VRAM (Lazy Load)...")
        app_data = os.getenv('LOCALAPPDATA')
        if not app_data: app_data = "/root/.local/share" 
        
        # Path standard di Coqui
        model_path = os.path.join(app_data, "tts", "tts_models--multilingual--multi-dataset--xtts_v2")
        
        # Download automatico se manca
        if not os.path.exists(model_path):
            print("Scaricamento modello...")
            TTS("tts_models/multilingual/multi-dataset/xtts_v2")
        
        # Init Config e Modello
        self.config = XttsConfig()
        self.config.load_json(os.path.join(model_path, "config.json"))
        
        self.model = Xtts.init_from_config(self.config)
        self.model.load_checkpoint(self.config, checkpoint_dir=model_path, eval=True)
        
        # Spostamento su GPU se disponibile
        if torch.cuda.is_available():
            self.model.cuda()
            print("XTTS caricato su GPU")
        else:
            print("XTTS su CPU")

    def release_memory(self):
        """
        [CRITICO] Rilascia la memoria GPU occupata dal modello.
        Da chiamare SEMPRE alla fine della generazione (pattern 'finally').
        """
        if self.model is not None:
            print("Rilascio VRAM XTTS...")
            self.model.cpu() # Sposta in RAM prima di cancellare
            del self.model
            self.model = None
            self.config = None
            
            # Forza Garbage Collector e svuota cache CUDA
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    def generate_audio(self, text: str, output_filename: str, chunks: list[str] = None) -> bool:
        """
        Orchestra l'intero processo di generazione audio.

        Args:
            text (str): Il testo completo (usato per il fallback se chunks è None).
            output_filename (str): Percorso file di output (es. 'output.mp3').
            chunks (list[str], optional): Lista di segmenti di testo pre-calcolati dall'LLM. 
                                          Se forniti, migliora drasticamente la prosodia.

        Returns:
            bool: True se la generazione è riuscita, False altrimenti.
        """
        
        # --- 1. Logica Fallback Chunks ---
        # XTTS ha un limite di input (~250 token). Dobbiamo spezzare il testo.
        chunks_to_use = chunks
        if not chunks_to_use:
            print("CoquiTTS: Chunks non forniti, calcolo locale in corso...")
            chunks_to_use = smart_chunking(text)
            
        if not chunks_to_use:
            print("Errore: Nessun testo da elaborare")
            return False

        self._load_model()

        # File di riferimento per la clonazione della voce
        voice_path = global_settings.tts_voice_file 
        if not os.path.exists(voice_path):
            print(f"Errore: File voce non trovato in {voice_path}")
            return False
        
        is_mp3 = output_filename.endswith(".mp3")
        wav_temp = output_filename.replace(".mp3", ".wav") if is_mp3 else output_filename
        
        generated_tensors = []
        sample_rate = 24000 # Sample rate nativo di XTTS

        try:
            with torch.no_grad(): # Disabilita gradienti per risparmiare memoria
                
                # Creazione Tensore Silenzio (Pausa tra le frasi)
                silence_frames = int(sample_rate * self.SENTENCE_PAUSE_S)
                silence_tensor = torch.zeros(1, silence_frames)
                if torch.cuda.is_available():
                    silence_tensor = silence_tensor.cuda()

                print(f"XTTS: Elaborazione di {len(chunks_to_use)} chunks...")

                # --- 2. LOOP DI SINTESI (Chunk by Chunk) ---
                for i, text_chunk in enumerate(chunks_to_use):
                    clean_text = self.normalizer.clean_text(text_chunk)
                    if not clean_text.strip(): continue

                    # Generazione Waveform
                    outputs = self.model.synthesize(
                        clean_text,
                        self.config,
                        speaker_wav=voice_path,
                        language="it",
                        gpt_cond_len=self.GPT_COND_LEN,
                        speed=self.GEN_SPEED,
                        temperature=self.TEMP,
                        repetition_penalty=self.REP_PENALTY,
                        top_k=self.TOP_K,
                        top_p=self.TOP_P,
                        enable_text_splitting=False, # Gestiamo noi lo splitting
                        do_sample=True
                    )
                    
                    # Conversione output in tensore
                    wav_tensor = torch.tensor(outputs["wav"]).unsqueeze(0)
                    if torch.cuda.is_available():
                        wav_tensor = wav_tensor.cuda()
                    
                    generated_tensors.append(wav_tensor)
                    
                    # Aggiunta silenzio se non è l'ultimo chunk
                    if i < len(chunks_to_use) - 1:
                        generated_tensors.append(silence_tensor)

                if not generated_tensors:
                    raise Exception("Nessun audio generato (chunks vuoti?)")

                # --- 3. STITCHING (Unione Tensori) ---
                full_audio = torch.cat(generated_tensors, dim=1)

                # --- 4. DSP POST-PROCESSING ---
                full_audio = full_audio.cpu() # Spostiamo su CPU per torchaudio transforms

                # A. Pitch Shift (opzionale)
                if self.PITCH_STEPS != 0:
                    pitch_shifter = T.PitchShift(sample_rate=sample_rate, n_steps=self.PITCH_STEPS)
                    full_audio = pitch_shifter(full_audio)

                # B. Normalizzazione Volume (evita clipping)
                max_val = torch.abs(full_audio).max()
                if max_val > 0: full_audio = full_audio / max_val * 0.95

                # C. Resampling (24k -> 44.1k Hi-Fi)
                resampler = T.Resample(orig_freq=sample_rate, new_freq=44100, dtype=torch.float32)
                wav_hq = resampler(full_audio)
                
                # Salvataggio WAV temporaneo a 32-bit float
                torchaudio.save(wav_temp, wav_hq, 44100, bits_per_sample=32)

            # --- 5. ENCODING FINALE ---
            if is_mp3:
                # Usa ffmpeg (tramite pydub o simile nella classe AudioConverter)
                AudioConverter.convert_wav_to_mp3(wav_temp)
                success = os.path.exists(output_filename)
            else:
                success = True

        except Exception as e:
            print(f"Errore XTTS Multi-Chunk: {e}")
            # Cleanup file parziali
            if os.path.exists(wav_temp):
                try: os.remove(wav_temp)
                except: pass
            success = False
        
        finally:
            # --- 6. SAFETY CLEANUP ---
            # Fondamentale per non bloccare la GPU per le prossime richieste
            self.release_memory()
        
        return success