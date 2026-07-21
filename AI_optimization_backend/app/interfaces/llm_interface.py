from abc import ABC, abstractmethod

class LLMInterface(ABC):
    @abstractmethod
    def generate(self, prompt: str, system_prompt: str = None) -> str:
        pass