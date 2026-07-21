import ollama
from app.interfaces.llm_interface import LLMInterface
from app.app_config import global_settings

class OllamaLLM(LLMInterface):
    
    def __init__(self, model_name: str = None, model: str = None):
        """
        Inizializza il plugin.
        Accetta sia 'model_name' che 'model' per compatibilità.
        """
        # Prende il primo valore non nullo tra: model_name, model, o il default dai settings
        self.model_name = model_name or model or global_settings.llm_model_name

    def generate(self, prompt: str, system_prompt: str = "Sei un assistente utile.") -> str:
        print(f"OLLAMA: Sto generando usando il modello: {self.model_name}")
        
        try:
            response = ollama.chat(
                model=self.model_name,
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': prompt},
                ]
            )
            return response['message']['content']
        except Exception as e:
            print(f"OLLAMA ERROR: {e}")
            return "Errore nella generazione del testo."