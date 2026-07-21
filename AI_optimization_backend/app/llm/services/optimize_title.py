import json
from app.schemas import TitleResponse
from app.llm.factory import LLMFactory  

def generate_optimized_title(original_title: str, model_name: str = "llama3.1:8b") -> TitleResponse:
    """
    Genera varianti creative (Copywriting) di un titolo turistico utilizzando un LLM.

    Questa funzione trasforma un titolo generico (es. "Chiesa San Marco") in opzioni 
    più accattivanti per un'app mobile (es. "I Segreti di San Marco").
    Utilizza tecniche di Prompt Engineering per forzare l'output in formato JSON 
    strutturato, facilitando il parsing da parte del backend.

    Args:
        original_title (str): Il titolo originale da migliorare.
        model_name (str, optional): Il modello da usare. Default: "llama3.1:8b".

    Returns:
        TitleResponse: Oggetto contenente:
            - options: Lista di 3 varianti (Corto, Evocativo, Domanda).
            - best_option: La variante consigliata dall'AI.
            - original: Il titolo di partenza.

    Behavior:
        - **JSON Enforcement:** Il prompt include istruzioni rigide per ottenere solo JSON valido.
        - **Sanitization:** Pulisce l'output da eventuali marcatori Markdown (```json).
        - **Defensive Parsing:** Controlla che ogni opzione sia una stringa pura. Se il modello
          sbaglia e restituisce oggetti annidati, il codice tenta di estrarne comunque il testo.
        - **Fallback:** In caso di JSON malformato o errore di rete, restituisce il titolo 
          originale come unica opzione, garantendo che l'UI non rimanga vuota.
    """

    # --- 1. PERSONA & STILE (Persona Pattern) ---
    # Definiamo chi sta parlando per influenzare lo stile delle risposte.
    system_role = (
        "Sei uno storico dell'arte specializzato in turismo ed in storytelling. "
        "Il tuo stile è conciso, evocativo e moderno. "
        "Il tuo pubblico sono turisti curiosi che usano lo smartphone per visualizzare i contenuti in AR. "
        "I titoli devono catturarli in meno di 1 secondo. "
        "Evita linguaggio troppo accademico o troppo formale."
    )

    # --- 2. TEMPLATE JSON (Format Constraint Pattern) ---
    # Forniamo un esempio esplicito di cosa ci aspettiamo per ridurre errori di parsing.
    json_template = """
    FORMATO OUTPUT RICHIESTO (JSON PURO):
    Devi restituire SOLO un oggetto JSON con questa struttura esatta:
    {
        "options": [
            "Titolo Corto & Punchy (Max 25 car)",
            "Titolo Evocativo/Misterioso",
            "Titolo Domanda/Ingaggio"
        ],
        "best_option": "La migliore delle tre"
    }
    """

    # --- 3. USER PROMPT ---
    user_prompt = f"""
    ANALISI CONTESTO: Il titolo attuale '{original_title}' è troppo generico o poco attraente.
    OBIETTIVO: Generare varianti che spingano l'utente a cliccare per saperne di più.
    
    TASK: Riscrivi il titolo '{original_title}'.
    
    {json_template}
    
    Rispondi SOLO col JSON, nessun altro commento.
    """

    print(f"Ottimizzazione titolo '{original_title}' in corso...")

    try:
        llm_engine = LLMFactory.get_engine(model_name)
        
        # Generazione Raw
        raw_content = llm_engine.generate(prompt=user_prompt, system_prompt=system_role)
        
        # --- 4. CLEANING & PARSING ---
        # Rimuove i backticks tipici delle risposte Markdown (es. ```json ... ```)
        clean_json = raw_content.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_json)
        
        # --- 5. DATA NORMALIZATION (Defensive Programming) ---
        # A volte i modelli piccoli (7b) sbagliano formato e mettono dizionari dentro la lista.
        # Questo ciclo normalizza tutto in stringhe semplici.
        raw_options = data.get("options", [original_title])
        sanitized_options = []
        
        for item in raw_options:
            if isinstance(item, str):
                sanitized_options.append(item)
            elif isinstance(item, dict):
                # Se è un dizionario (es. {'text': 'Titolo'}), prendiamo il primo valore
                val = list(item.values())[0] if item else original_title
                sanitized_options.append(str(val))
            else:
                sanitized_options.append(str(item))

        return TitleResponse(
            original=original_title,
            options=sanitized_options,
            best_option=data.get("best_option", original_title),
            model_used=model_name,
            success=True,
            error_message=None
        )

    except Exception as e:
        error_str = str(e)
        print(f"Errore generazione titoli: {error_str}")

        friendly_error = "Errore generico AI durante la generazione dei titoli."

        if "Connection refused" in error_str or "No connection" in error_str:
            friendly_error = "Impossibile connettersi a Ollama. Assicurati che sia attivo."
        elif "model" in error_str and "not found" in error_str:
            friendly_error = "Modello LLM non trovato sul server."
        elif isinstance(e, json.JSONDecodeError):
            friendly_error = "Il modello ha restituito un JSON malformato."

        # --- FALLBACK ---
        # Se tutto fallisce, l'utente vede il titolo originale.
        return TitleResponse(
            original=original_title,
            options=[original_title], 
            best_option=original_title,
            model_used=f"Error ({model_name}) - Fallback",
            success=False,
            error_message=f"{friendly_error} (Dettagli: {error_str})"
        )