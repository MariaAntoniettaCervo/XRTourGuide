from app.llm.plugins.ollama_plugin import OllamaLLM

class LLMFactory:
    """
    Centralizza la creazione delle istanze per i Large Language Models (Text Generation).

    Pattern: **Simple Factory**

    Obiettivo:
    Disaccoppiare la logica di business (es. "genera un titolo") dalla specifica
    implementazione tecnologica (es. "chiama l'API di Ollama").
    Il resto dell'app non sa (e non deve sapere) che stiamo usando Ollama;
    sa solo che riceve un oggetto capace di generare testo.

    Nota su model_name:
    A differenza di TTSFactory (insieme chiuso di motori), qui l'insieme dei modelli
    è aperto e determinato dal runtime Ollama: nessuna validazione lato factory.
    Il valore è già vincolato a monte da LLMModelEnum (schemas.py); un modello
    inesistente lato Ollama è gestito dal fallback in OllamaLLM.generate.

    Future-Proofing:
    Se in futuro si vorrà aggiungere OpenAI o Azure, basterà aggiungere un 'if' qui.
    """

    @staticmethod
    def get_engine(model_name: str): 
        """
        Restituisce un client LLM configurato.

        Args:
            model_name (str): Il nome del modello (es. "qwen2.5:7b", "llama3.1:8b").
                              Passato direttamente al plugin per il routing, senza
                              validazione lato factory.

        Returns:
            OllamaLLM: Un'istanza del wrapper che comunica con il demone Ollama locale.
        """
                
        return OllamaLLM(model=model_name)