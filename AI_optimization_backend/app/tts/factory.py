from app.tts.plugins.coqui_engine import CoquiTTS    
from app.tts.plugins.piper_engine import PiperTTS    
from app.interfaces.tts_interface import TTSInterface

class TTSFactory:
    """
    Gestisce la creazione e il ciclo di vita dei motori di Sintesi Vocale.
    
    Implementa il 'Factory Pattern' per disaccoppiare la logica di business 
    (che vuole solo 'generare audio') dalla complessità di inizializzazione 
    dei singoli motori (caricamento pesi, configurazione path, ecc.).

    Key Feature: **Memory Management Strategy**
    - Per motori pesanti (Coqui XTTS), implementa un pattern **Singleton** per mantenere
      il modello in VRAM tra una richiesta e l'altra.
    - Per motori leggeri (Piper), crea nuove istanze on-demand poiché non hanno stato persistente.
    """
    
    # Variabile di classe per cachare l'istanza pesante
    _coqui_instance = None

    @staticmethod
    def get_engine(engine_type: str) -> TTSInterface:
        """
        Restituisce l'istanza del motore TTS richiesto.

        Args:
            engine_type (str): Identificatore del motore (es. 'coqui-xtts', 'piper').
                               Corrisponde ai valori dell'Enum TTSModelEnum.

        Returns:
            TTSInterface: Un oggetto che implementa il metodo .generate_audio().
        
        Raises:
            ValueError: Se l'engine richiesto non è implementato.
        """
        
        # --- CASO 1: HIGH QUALITY / HEAVY (GPU) ---
        if engine_type == "coqui-xtts":  
            # Singleton Pattern:
            # Se l'abbiamo già caricato in passato, restituiamo quello.
            # Altrimenti, paghiamo il costo di inizializzazione (alcuni secondi) ora.
            if TTSFactory._coqui_instance is None:
                print("FACTORY: Caricamento modello Coqui in memoria (Cold Start)...")
                TTSFactory._coqui_instance = CoquiTTS()
            
            return TTSFactory._coqui_instance
            
        # --- CASO 2: HIGH SPEED / LIGHT (CPU) ---
        elif engine_type == "piper":
            # Transient Pattern:
            # Piper è solo un wrapper di un comando 'subprocess'. 
            # L'oggetto Python pesa pochi byte, quindi possiamo ricrearlo ogni volta
            # senza impatti sulle performance.
            return PiperTTS()
            
        else:
            # Fallback di sicurezza
            raise ValueError(f"Engine TTS sconosciuto o non supportato: {engine_type}")