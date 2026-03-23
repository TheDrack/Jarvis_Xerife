from abc import ABC, abstractmethod

class VoicePort(ABC):
    @abstractmethod
    async def stt(self, audio_bytes: bytes) -> str:
        """Speech-to-Text: Converte áudio em texto."""
        pass

    @abstractmethod
    async def tts(self, text: str) -> bytes:
        """Text-to-Speech: Converte texto em áudio."""
        pass
