from abc import ABC, abstractmethod
from typing import List, Optional

class TTSInterface(ABC):
    @abstractmethod
    def generate_audio(self, text: str, output_filename: str, chunks: Optional[List[str]] = None) -> bool:
        pass