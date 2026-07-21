import re

def smart_chunking(text: str, max_chars: int = 200) -> list[str]:
    """
    Divide un testo lungo in segmenti (chunks) ottimizzati per la sintesi vocale.

    I modelli TTS neurali (come Coqui XTTS) hanno una 'Context Window' limitata 
    (spesso circa 250-400 token). Se si invia un testo più lungo, il modello inizia 
    ad avere allucinazioni, degradare la qualità o tagliare l'audio.
    
    Questa funzione usa una strategia "Greedy" per riempire ogni chunk 
    fino al limite massimo, ma rispettando rigorosamente la fine delle frasi.

    Args:
        text (str): Il testo completo da processare.
        max_chars (int): Limite massimo di caratteri per singolo chunk. 
                         Default 200 è conservativo per garantire stabilità a XTTS.

    Returns:
        list[str]: Lista di stringhe pronte per essere inviate al TTS loop.
    """
    
    # 1. Pulizia Preliminare
    # Trasforma "Ciao    mondo" in "Ciao mondo"
    text = re.sub(r'\s+', ' ', text).strip()
    
    # 2. Splitting Intelligente (Regex Lookbehind)
    # Questa regex è il cuore della funzione.
    # (?<=[.!?]) -> "Positive Lookbehind": Significa "Taglia DOPO un punto, ma NON consumarlo".
    #               Mantiene il punto attaccato alla frase precedente.
    # \s+        -> Consuma gli spazi successivi al punto.
    sentences = re.split(r'(?<=[.!?])\s+|(?<=\.\.\.)\s+', text)
    
    chunks = []
    current_chunk = ""
    
    # 3. Algoritmo di Accumulo (Greedy Bin Packing)
    
    for sentence in sentences:
        if not sentence.strip(): continue
        
        # Se la frase corrente ci sta nel chunk attuale, aggiungila
        if len(current_chunk) + len(sentence) < max_chars:
            current_chunk += sentence + " "
        else:
            # Altrimenti, chiudi il chunk attuale (flush) e iniziane uno nuovo
            if current_chunk: chunks.append(current_chunk.strip())
            current_chunk = sentence + " "
            
    # Non dimenticare l'ultimo pezzo rimasto nel buffer!
    if current_chunk: chunks.append(current_chunk.strip())
    
    return chunks