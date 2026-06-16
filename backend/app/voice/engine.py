"""Voice engines (Phase 2): push-to-talk STT + local TTS.

faster-whisper (STT) and Piper (TTS) are imported lazily; absent deps raise a
clear, actionable error rather than crashing the app. In PRIVATE_MODE audio
never leaves the machine — both engines are local. Risky actions triggered by
voice still go through the normal approval queue (voice never bypasses it).
"""
from __future__ import annotations

from typing import Protocol


class SpeechToText(Protocol):
    def transcribe(self, audio_path: str) -> str: ...


class TextToSpeech(Protocol):
    def synthesize(self, text: str, out_path: str) -> str: ...


class FasterWhisperSTT(SpeechToText):
    def __init__(self, model: str = "base") -> None:
        self.model_name = model
        self._model = None

    def _load(self):  # pragma: no cover - heavy optional dep
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:  # noqa: BLE001
                raise RuntimeError("`pip install faster-whisper` to enable STT.") from exc
            self._model = WhisperModel(self.model_name)
        return self._model

    def transcribe(self, audio_path: str) -> str:  # pragma: no cover - needs audio
        model = self._load()
        segments, _ = model.transcribe(audio_path)
        return " ".join(s.text for s in segments).strip()


class PiperTTS(TextToSpeech):
    def __init__(self, voice: str = "en_US-amy-medium") -> None:
        self.voice = voice

    def synthesize(self, text: str, out_path: str) -> str:  # pragma: no cover - needs piper
        try:
            import shutil
            import subprocess
        except ImportError as exc:  # noqa: BLE001
            raise RuntimeError("Piper TTS unavailable.") from exc
        if shutil.which("piper") is None:
            raise RuntimeError("Install the Piper binary + a voice to enable TTS.")
        subprocess.run(
            ["piper", "--model", self.voice, "--output_file", out_path],
            input=text.encode(), check=True,
        )
        return out_path


def is_voice_available() -> bool:
    """True if at least the STT dependency is importable."""
    try:
        import faster_whisper  # noqa: F401

        return True
    except ImportError:
        return False
