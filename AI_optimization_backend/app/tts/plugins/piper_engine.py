import subprocess
import os
import sys
import importlib.util
from app.interfaces.tts_interface import TTSInterface
from app.tts.text_normalizer import TextNormalizer

class PiperTTS(TTSInterface):
    """
    Wrapper per il motore TTS 'Piper' (Lightweight & Fast).

    A differenza di Coqui (che gira in-process), questa classe agisce come un 
    orchestratore di processi CLI. Esegue il binario di Piper per generare l'audio 
    e successivamente FFmpeg per la codifica, mantenendo il consumo di RAM 
    vicino allo zero quando non è in uso.

    Features:
    - **Self-Healing Dependency:** Controlla e installa automaticamente la libreria `piper-tts` se mancante.
    - **Process Isolation:** L'eventuale crash del motore C++ di Piper non fa crashare il server Python principale.
    - **Zero-Idle RAM:** Non mantiene modelli caricati in memoria tra una richiesta e l'altra.
    
    Attributes:
        model_path (str): Percorso assoluto al file .onnx del modello vocale.
        ffmpeg_path (str): Percorso dell'eseguibile FFmpeg (locale o di sistema).
    """

    def __init__(self):
        print("Inizializzazione Plugin Piper TTS...")
        
        # --- AUTO-INSTALLAZIONE LIBRERIA (Self-Healing) ---
        # Verifica se l'ambiente ha i pacchetti necessari, altrimenti li scarica al volo.
        self._ensure_piper_installed()

        # 1. Calcolo Percorsi Assoluti
        # Risaliamo la struttura delle directory per trovare la root del progetto
        current_dir = os.path.dirname(os.path.abspath(__file__)) 
        tts_dir = os.path.dirname(current_dir)                   
        app_dir = os.path.dirname(tts_dir)                       
        self.project_root = os.path.dirname(app_dir)             
        
        # 2. Percorso Modello (Piper richiede path assoluti per sicurezza)
        self.model_path = os.path.join(self.project_root, "models", "it_IT-paola-medium.onnx")
        
        if not os.path.exists(self.model_path):
            print(f"ATTENZIONE: Modello Piper non trovato in: {self.model_path}")
            print("   -> Scaricalo e mettilo nella cartella 'models/'.")

        # 3. Percorso FFmpeg
        # Cerchiamo prima un ffmpeg locale (per deployment portatili), poi quello di sistema
        self.ffmpeg_path = os.path.join(self.project_root, "bin", "ffmpeg.exe")
        
        if not os.path.exists(self.ffmpeg_path):
            self.ffmpeg_path = "ffmpeg" # Fallback al PATH di sistema

        self.normalizer = TextNormalizer()

    def _ensure_piper_installed(self):
        """
        Controlla la presenza della libreria 'piper-tts'.
        Se assente, lancia un sottoprocesso pip per installarla senza riavviare il server.
        """
        spec = importlib.util.find_spec("piper")
        
        if spec is None:
            print("Libreria 'piper-tts' mancante. Installazione automatica in corso...")
            try:
                # Esegue 'pip install piper-tts' usando lo stesso interprete Python attivo
                subprocess.check_call([sys.executable, "-m", "pip", "install", "piper-tts"])
                print("Libreria Piper installata con successo!")
            except subprocess.CalledProcessError as e:
                print(f"ERRORE CRITICO: Impossibile installare piper-tts automaticamente.\nEsegui manualmente: pip install piper-tts\nDettagli: {e}")

    def generate_audio(self, text: str, output_filename: str, chunks: list = None, **kwargs) -> bool:
        """
        Esegue la pipeline di generazione: Normalizzazione -> Piper (WAV) -> FFmpeg (MP3).

        Args:
            text (str): Il testo da leggere.
            output_filename (str): Path finale del file audio.
            chunks (list, optional): Ignorato da Piper (che gestisce lo stream internamente), 
                                     ma mantenuto per compatibilità con l'interfaccia.

        Returns:
        bool: True se il file audio è stato generato correttamente, False in caso di
              errore (subprocess fallito, file non creato, ecc.). Eventuali eccezioni
              vengono catturate internamente e non propagate, rispettando il contratto
              dichiarato da TTSInterface.generate_audio.

        """
        
        # --- NORMALIZZAZIONE ---
        testo_processato = self.normalizer.clean_text(text)
        
        is_mp3 = output_filename.endswith(".mp3")
        # Piper genera solo WAV raw. Se serve MP3, usiamo un file temporaneo.
        wav_temp = output_filename.replace(".mp3", ".wav") if is_mp3 else output_filename
        
        # Costruzione comando CLI
        # Eseguiamo piper come modulo (python -m piper) per evitare problemi di PATH
        comando_piper = [
            sys.executable, "-m", "piper",
            "--model", self.model_path,
            "--output_file", wav_temp,
            "--sentence_silence", "0.5" # Pausa fissa tra frasi
        ]

        # Configurazione ambiente per UTF-8 
        # CRITICO SU WINDOWS: Senza questo, le lettere accentate italiane fanno crashare la pipe.
        my_env = os.environ.copy()
        my_env["PYTHONUTF8"] = "1"
        my_env["PYTHONIOENCODING"] = "utf-8"

        try:
            # 1. Genera WAV con Piper (Subprocess Blocking)
            subprocess.run(
                comando_piper, 
                input=testo_processato.encode('utf-8'),
                env=my_env,
                check=True,
                stdout=subprocess.DEVNULL, # Silenzia output standard per pulizia log
                stderr=subprocess.PIPE     # Cattura errori per debugging
            )
            
            # Se l'output richiesto era WAV, abbiamo finito
            if not is_mp3:
                return os.path.exists(wav_temp)

            # 2. Conversione MP3 con FFmpeg
            if os.path.exists(wav_temp):
                comando_ffmpeg = [
                    self.ffmpeg_path,
                    "-i", wav_temp,
                    "-y",                 # Sovrascrivi senza chiedere
                    "-b:a", "128k",       # Bitrate standard per voce
                    "-af", "adelay=200|200", # Aggiunge 200ms di silenzio all'inizio (anti-clipping player)
                    output_filename
                ]
                
                subprocess.run(
                    comando_ffmpeg,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    check=True
                )
                
                # --- PULIZIA ---
                # Rimuoviamo il WAV pesante intermedio
                try:
                    os.remove(wav_temp)
                except Exception as e:
                    print(f"Impossibile rimuovere temp wav: {e}")
                
                if os.path.exists(output_filename):
                    return True
            
            print("Errore Piper: conversione MP3 fallita (file non creato)")
            return False
        
        except subprocess.CalledProcessError as e:
            # Decodifica l'errore dallo stderr del sottoprocesso
            err_msg = e.stderr.decode('utf-8', errors='ignore')
            print(f"Errore Processo Piper/FFmpeg: {err_msg}")
            return False 
         
        except Exception as e:
            print(f"Errore Generico Piper Plugin: {e}")
            return False