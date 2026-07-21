import re

class TextNormalizer:

    """
    Pre-processore linguistico per ottimizzare il testo per la Sintesi Vocale (TTS).

    Il suo compito principale è trasformare termini ambigui, acronimi, 
    parole straniere o latine nella loro **rappresentazione fonetica italiana**.
    
    Perché è necessario?
    I modelli TTS (come Piper o Coqui) addestrati in italiano spesso:
    1. Leggono l'inglese "come si scrive" (es. "Wi-Fi" -> "Vifi").
    2. Sbagliano l'accento sulle parole latine (es. "Insula" -> "Insulà").
    3. Non sanno espandere le abbreviazioni (es. "d.C." -> "dici").

    Questa classe risolve questi problemi prima ancora che l'audio venga generato.
    """

    def __init__(self):
        self.replacements = {}
        
        # 1. TECNOLOGIA & INGLESE
        self.replacements.update({
            "xrtourguide": "ecs ar tur gaid",
            "futural": "fiu ciur al",
            "wi-fi": "uai fai",
            "ticket": "ticchet",
            "check-in": "cec in",
            "hall": "oll",
            "online": "on lain",
            "offline": "off lain",
            "touch": "tac",
            "location": "lochescion",
            "xr": "ecs ar",
        })

        # 2. LATINO & MEDIEVALE (Architettura e Arte)
        self.replacements.update({
            "domus": "dòmus",           
            "insula": "ìnsula",
            "insulae": "ìnsule",        
            "castrum": "càstrum",
            "cardus": "càrdus",
            "decumanus": "decumànus",
            "forum": "fòrum",
            "basilica": "basìlica",     
            "atrium": "àtrium",
            "tablinum": "tablìnum",
            "triclinium": "triclìnium",
            "frigidarium": "frigidàrium",
            "calidarium": "calidàrium",
            "tepidarium": "tepidàrium",
            "vomitorium": "vomitòrium",
            "cavea": "càvea",
            "opus": "òpus",             
            "reticulatum": "reticulàtum",
            "incertum": "incèrtum",
            "fresco": "frèsco",
            "affresco": "affrèsco",
            "velarium": "velàrium",
            "lapidarium": "lapidàrium",
        })

        # 3. TERMINI ECCLESIASTICI
        self.replacements.update({
            "sanctus": "sànctus",
            "pater": "pàter",
            "filius": "fìlius",
            "spiritus": "spìritus",
            "amen": "àmen",
            "gloria": "glòria",
            "magnificat": "magnìficat", 
            "requiem": "rècuiem",       
            "ecclesia": "ecclèsia",
            "cattedrale": "cattedràle",
            "duomo": "duòmo",
            "pieve": "piève",
            "presbiterio": "presbitèrio",
            "abside": "àbside",         
            "navata": "navàta",
            "transetto": "transètto",
            "cripta": "crìpta",
            "nartece": "nàrtece",
        })

        # 4. ESPRESSIONI STORICHE & DATAZIONE
        self.replacements.update({
            "anno domini": "ànno dòmini",
            "ante christum": "ànte crìstum",
            "post christum": "pòst crìstum",
            "hic iacet": "hic iàcet",   
            "spqr": "esse pi qu erre",  
            "s.p.q.r.": "esse pi qu erre",
            "et": "et",                 
            "item": "ìtem",
            "ibidem": "ibìdem",
            "ex voto": "ecs vòto",
            
            # VARIANTI DATE
            "d.c.": "dopo cristo",
            "d.c": "dopo cristo",
            "a.c.": "avanti cristo",
            "a.c": "avanti cristo",
            "dc": "dopo cristo",
            "ac": "avanti cristo",
            "sec.": "secolo",
        })

    def _apply_replacements(self, text: str) -> str:
        """Applica le sostituzioni dal dizionario usando Regex intelligenti"""
        for original, phonetic in self.replacements.items():
            pattern = r'(?i)' # Case insensitive
            
            # Se inizia con alfanumerico, usa boundary \b per non sostituire parti di parola
            if original[0].isalnum():
                pattern += r'\b'
            
            pattern += re.escape(original)
            
            # Se finisce con alfanumerico, usa boundary \b.
            # Se finisce con punto (es "d.c."), NON usiamo \b perché il punto è già un delimitatore
            if original[-1].isalnum():
                pattern += r'\b'
            
            text = re.sub(pattern, phonetic, text)
        return text

    def clean_text(self, text: str) -> str:
        """Pipeline principale di pulizia"""
        
        # 1. RIMOZIONE MARKDOWN E EMOJI
        text = re.sub(r'[\*\#\[\]\_\-]', '', text) # Via markdown (*, #, _, -)
        
        # Mantiene solo lettere, numeri e punteggiatura base. Via Emoji.
        text = re.sub(r'[^\w\s\.,!\?;:àèéìòùÀÈÉÌÒÙ\'"]', '', text)

        # 2. NORMALIZZAZIONE DIZIONARIO (Latino, date, tech)
        text = self._apply_replacements(text)

        # 3. PULIZIA SPAZI
        text = re.sub(r'\s+', ' ', text).strip()
        
        # 4. GESTIONE PUNTEGGIATURA FINALE (Specifico per XTTS)
        # Se finisce con un punto, lo togliamo e mettiamo un a capo
        # Questo evita che l'AI dica la parola "punto" alla fine.
        if text.endswith((".", "!", "?")):
            text = text[:-1]
        
        return text + "\n"

# --- ESEMPIO DI UTILIZZO ---
if __name__ == "__main__":
    norm = TextNormalizer()
    test_phrases = [
        "Benvenuti nel 2024 d.C. alla Domus.",
        "Il Wi-Fi si trova nella hall.",
        "Opus reticulatum del I sec. a.C.",
        "XRTourGuide è online!"
    ]
    
    print("--- TEST NORMALIZZAZIONE ---")
    for t in test_phrases:
        print(f"IN : {t}")
        print(f"OUT: '{norm.clean_text(t)}'") # Le virgolette mostrano il \n finale