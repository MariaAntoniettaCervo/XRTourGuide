from app.llm.factory import LLMFactory
from app.schemas import DescriptionResponse

def generate_optimized_description(original_text: str, model_name: str = "llama3.1:8b") -> DescriptionResponse:
    """
    Riscrive una descrizione turistica ottimizzandola per l'ascolto (Storytelling Audio).

    Questa funzione utilizza un LLM per trasformare un testo grezzo o breve in una narrazione
    coinvolgente, stile "divulgatore culturale".

    
    Args:
        original_text (str): Il testo di input (es. "Statua del 1500 in marmo").
        model_name (str, optional): Il modello LLM da utilizzare (default: "llama3.1:8b").

    Returns:
        DescriptionResponse: Un oggetto contenente:
            - full_text_optimized (str): Il testo riscritto dall'AI.
            - model_used (str): Il nome del modello utilizzato.

    Behavior:
        - **Persona:** Agisce come un esperto d'arte carismatico.
        - **Fact-Checking:** Include istruzioni esplicite per evitare allucinazioni su date/nomi.
        - **Fallback:** In caso di errore dell'LLM (timeout, crash), restituisce il testo originale
          senza ottimizzazioni per garantire la continuità del servizio.
    """
    
    system_role = (
        "Sei un Divulgatore Culturale esperto e carismatico (stile Alberto Angela). "
        "Scrivi per un'applicazione di Realtà Aumentata che guida i turisti in Italia. "
        "Il tuo italiano è fluido, elegante ed evocativo. "
        "Il tuo obiettivo è emozionare l'utente, facendogli notare la bellezza di ciò che ha davanti."
    )

    guidelines = """
    LINEE GUIDA UNIVERSALI:
    1. NO ANACRONISMI: Fai estrema attenzione ai materiali e alle tecnologie. Non citare materiali moderni se l'opera è antica o rinascimentale.
    2. FOCUS SUL VISIBILE: Descrivi l'impatto visivo del monumento (le dimensioni, i materiali, i giochi di luce, i colori). Invita l'utente a guardare i dettagli.
    3. GRAMMATICA IMPECCABILE: Evita frasi passive, ripetizioni o traduzioni letterali. Usa un lessico ricco ma comprensibile.
    4. ESPANSIONE INTELLIGENTE: Usa il 'Testo di Base' come fonte di verità. Puoi arricchirlo con dettagli atmosferici o contesto storico generale, ma NON inventare date o nomi specifici se non sei sicuro al 100%.
    """

    fact_checking_protocol = """
    PROTOCOLLO DI FACT-CHECKING E VERITÀ STORICA (PRIORITÀ ASSOLUTA):
    1. Poiché devi espandere il testo, userai le tue conoscenze interne. FAI ATTENZIONE.
    2. VERIFICA ogni data, nome di imperatore o evento storico che aggiungi. Devono essere REALI.
    3. NON INVENTARE MAI DETTAGLI. Se non sei sicurissimo di un anno specifico, usa termini più generici (es. "all'inizio del primo secolo") piuttosto che rischiare un numero sbagliato.
    4. Se il testo originale contiene un errore palese, correggilo basandoti sulla tua conoscenza enciclopedica.
    """

    constraints = """
    VINCOLI DI LUNGHEZZA E FORMATO (OBBLIGATORI):
    1. LUNGHEZZA: Devi generare un testo di ALMENO 130-150 parole. Se il testo originale è breve, USA LE TUE CONOSCENZE per arricchirlo con dettagli storici, curiosità e descrizioni visive pertinenti.
    2. AUDIO CLEANING:
       - Scrivi i numeri in lettere se necessario per la fluidità.
       - Niente parentesi, caratteri speciali o elenchi puntati.
       - NON usare MAI le virgolette (" ' « ») da nessuna parte nel testo, nemmeno
         per aprire o "mettere in scena" una frase come farebbe un narratore.
         Il testo è narrato direttamente in prima persona dal divulgatore, non
         è una citazione o un copione: scrivi le frasi senza racchiuderle tra
         virgolette di alcun tipo.
    3. Ogni frase deve avere senso compiuto.

    FORMATO DELL'OUTPUT (OBBLIGATORIO, NESSUNA ECCEZIONE):
    - La tua risposta deve iniziare DIRETTAMENTE con la prima parola della
      narrazione (es. "Benvenuti al Colosseo..."), MAI con un'introduzione,
      un titolo, o un commento su cosa stai per fare.
    - VIETATO iniziare con frasi come: "Ecco il testo ottimizzato:", "Ecco la
      descrizione:", "Testo ottimizzato:", "Certo, ecco...", o qualsiasi altra
      variante che annunci o commenti il contenuto prima di iniziarlo.
    - La tua risposta deve TERMINARE con l'ultima frase della narrazione
      stessa. Non aggiungere MAI, in nessuna forma o formulazione, un
      commento finale su te stesso, sul tuo lavoro, o sul fatto di aver
      seguito le istruzioni — anche se breve, anche se sembra utile o
      professionale. Questo vale per QUALSIASI frase che parli DEL testo
      invece di ESSERE il testo: non solo esempi come "Spero questo ti sia
      utile" o "Fammi sapere se...", ma anche cose come "Nota: ho seguito le
      linee guida...", "Come richiesto, il testo rispetta...", o qualsiasi
      altra osservazione, disclaimer o commento meta-testuale, in qualunque
      punto della risposta compaia.
    - Test da applicare a te stesso prima di rispondere: ogni singola frase
      che scrivi deve poter essere letta ad alta voce dal narratore come
      parte della visita guidata. Se una frase non avrebbe senso detta da un
      narratore che sta accompagnando un turista davanti al monumento (perché
      parla DI te, del compito, o del testo stesso), quella frase va rimossa.
    - L'intera risposta deve contenere ESCLUSIVAMENTE il testo narrato, dalla
      prima all'ultima parola, pronto per essere letto ad alta voce così com'è.
    """

    user_prompt = f"""
    {system_role}
    
    TESTO ORIGINALE: "{original_text}"
    
    Compito: Riscrivi il testo rendendolo accattivante.
    {guidelines}
    {fact_checking_protocol}
    {constraints}
    
    Rispondi SOLO con il testo ottimizzato, seguendo esattamente il FORMATO
    DELL'OUTPUT sopra indicato: nessuna introduzione, nessuna virgoletta,
    nessun commento finale.
    """

    try:
        llm_engine = LLMFactory.get_engine(model_name)
        raw_content = llm_engine.generate(prompt=user_prompt, system_prompt=system_role)

        return DescriptionResponse(
            full_text_optimized=raw_content,
            model_used=model_name,
            success=True,
            error_message=None
        )

    except Exception as e:
        error_str = str(e)
        print(f"Errore LLM Descrizione: {error_str}")

        friendly_error = "Errore generico AI durante la generazione della descrizione."
        if "Connection refused" in error_str or "No connection" in error_str:
            friendly_error = "Impossibile connettersi a Ollama. Assicurati che sia attivo."
        elif "model" in error_str and "not found" in error_str:
            friendly_error = "Modello LLM non trovato sul server."

        return DescriptionResponse(
            full_text_optimized=original_text,
            model_used=f"Error ({model_name}) - Fallback to Original",
            success=False,
            error_message=f"{friendly_error} (Dettagli: {error_str})"
        )