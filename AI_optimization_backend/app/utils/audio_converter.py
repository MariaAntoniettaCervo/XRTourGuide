import os
import sys
from pydub import AudioSegment, AudioSegment

class AudioConverter:
    
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))
    
    FFMPEG_LOCAL_PATH = os.path.join(PROJECT_ROOT, "bin", "ffmpeg.exe")

    if os.path.exists(FFMPEG_LOCAL_PATH):
        AudioSegment.converter = FFMPEG_LOCAL_PATH
        AudioSegment.ffmpeg = FFMPEG_LOCAL_PATH
        print(f"AudioConverter: Uso FFmpeg locale in {FFMPEG_LOCAL_PATH}")
    else:
        # Cerco FFMPEG nel sistema
        print("AudioConverter: FFmpeg locale non trovato in 'bin'. Provo quello di sistema...")

    @staticmethod
    def convert_wav_to_mp3(wav_path: str, bitrate: str = "192k") -> str:
        """
        Converte WAV in MP3 usando pydub (che chiama ffmpeg.exe).
        Cancella il WAV originale.
        """
        if not os.path.exists(wav_path):
            print(f"File WAV non trovato: {wav_path}")
            return ""

        mp3_path = wav_path.replace(".wav", ".mp3")
        
        try:
            audio = AudioSegment.from_wav(wav_path)
            
            # Export
            audio.export(
                mp3_path, 
                format="mp3", 
                bitrate=bitrate,
                parameters=["-q:a", "2"] 
            )
            
            # Pulizia
            if os.path.exists(wav_path):
                os.remove(wav_path)
            
            return mp3_path

        except Exception as e:
            print(f"Errore critico conversione MP3: {e}")
            print(f"Controlla che ffmpeg.exe sia in: {AudioConverter.FFMPEG_LOCAL_PATH}")
            # Se fallisce, ritorniamo il wav
            return wav_path

if __name__ == "__main__":
    print(f"Root Progetto stimata: {AudioConverter.PROJECT_ROOT}")