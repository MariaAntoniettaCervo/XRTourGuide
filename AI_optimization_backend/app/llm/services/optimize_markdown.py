from app.llm.factory import LLMFactory
from app.schemas import MarkdownFixResponse
import logging

def fix_markdown(text: str, tone: str, model_name: str = "llama3.1:8b") -> MarkdownFixResponse:
    """
    Esegue un proofreading intelligente del testo mantenendo la formattazione Markdown.

    Questa funzione agisce come un "Correttore di Bozze" automatico. Analizza il testo in input,
    corregge errori grammaticali e sintattici, adatta il tono di voce richiesto, ma
    **protegge rigorosamente la struttura Markdown** (bold, headers, liste) per evitare
    di rompere il rendering nel frontend.

    Args:
        text (str): Il testo originale (può contenere sintassi Markdown come **, #, -).
        tone (str): Il tono desiderato per la revisione (es. "professionale", "amichevole", "accademico").
        model_name (str, optional): Il modello LLM da utilizzare (default: "llama3.1:8b").

    Returns:
        MarkdownFixResponse: Un oggetto strutturato contenente:
            - original_text: Il testo inviato.
            - fixed_text: Il testo corretto (o l'originale in caso di errore).
            - success: Booleano che indica se l'LLM ha risposto correttamente.
            - error_message: Dettaglio dell'errore (se presente).

    Behavior:
        - **Format Preservation:** Il System Prompt istruisce esplicitamente il modello a non toccare i simboli Markdown.
        - **Error Mapping:** Traduce errori tecnici (es. "Connection refused") in messaggi user-friendly.
        - **Graceful Degradation:** In caso di crash dell'AI o di timeout, la funzione NON solleva eccezione
          ma restituisce il testo originale (`fixed_text = text`) con `success=False`.
          Questo garantisce che l'utente non perda mai il suo lavoro.
    """

    print(f"FIXING MARKDOWN (Tone: {tone})...")

    # --- 1. SYSTEM PROMPT (Role & Constraints Pattern) ---
    # Definisce il ruolo di Editor e impone la regola ferrea di preservare il Markdown.
    system_prompt = (
        "Sei un editor esperto e un correttore di bozze professionale. "
        "Il tuo compito è riscrivere il testo fornito dall'utente rispettando queste regole:\n"
        "1. Correggi errori grammaticali e di sintassi.\n"
        "2. Migliora la fluidità del testo mantenendo il significato originale.\n"
        "3. Mantieni o migliora la formattazione MARKDOWN (grassetto, elenchi, titoli).\n"
        "4. Non aggiungere commenti, introduzioni o saluti. Restituisci SOLO il testo corretto.\n"
        f"5. Adotta un tono: {tone}."
    )

    try:
        llm_engine = LLMFactory.get_engine(model_name)
        
        # Generazione (Zero-Shot)
        fixed_content = llm_engine.generate(prompt=text, system_prompt=system_prompt)
                
        return MarkdownFixResponse(
            original_text=text,
            fixed_text=fixed_content,
            success=True,
            error_message=None
        )

    except Exception as e:
        # --- 2. ERROR HANDLING & FALLBACK ---
        error_str = str(e)
        print(f"Errore LLM Fix: {error_str}")
        
        # Mapping errori tecnici -> Messaggi leggibili
        friendly_error = "Errore generico AI."
        if "Connection refused" in error_str or "No connection" in error_str:
            friendly_error = "Impossibile connettersi a Ollama. Assicurati che sia attivo."
        elif "model" in error_str and "not found" in error_str:
            friendly_error = "Modello LLM non trovato sul server."

        # CASO ERRORE: Restituiamo comunque il testo originale (Fallback)
        # Importante: Non blocchiamo l'utente, gli ridiamo il suo testo non modificato.
        return MarkdownFixResponse(
            original_text=text,
            fixed_text=text, # Fallback critico: restituiamo input
            success=False,
            error_message=f"{friendly_error} (Dettagli: {error_str})"
        )