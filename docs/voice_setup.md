# Voice Setup (Phase 2)

Voice is **push-to-talk first**, fully local, and uses the *same* approval system
as chat — speaking a command never bypasses approvals.

## Pipeline

```
mic → (push-to-talk) → STT → command text → Supervisor → … → answer → TTS → speaker
```

- **STT (speech-to-text):** `faster-whisper` (CTranslate2) or `whisper.cpp`,
  running locally. Model size configurable (`base`/`small`/`medium`).
- **TTS (text-to-speech):** **Piper** local voices. No cloud TTS by default.
- **Wake word:** later (Phase 4) via openWakeWord / Porcupine.

## Safety

- Risky actions require **voice confirmation** *and* the normal approval card.
- In `PRIVATE_MODE` audio never leaves the machine (local STT/TTS only).
- Transcripts are stored as `voice_sessions` with redaction applied.

## Config (`.env`)

```env
VOICE_ENABLED=false
STT_ENGINE=faster-whisper      # faster-whisper | whisper.cpp
STT_MODEL=base
TTS_ENGINE=piper
PIPER_VOICE=en_US-amy-medium
```

## Phase 1 status

Phase 1 ships the `voice/` package interface (`SpeechToText`, `TextToSpeech`
protocols) and the `voice_sessions` table, but engines are stubs that raise a
clear "enable in Phase 2" error unless the optional deps are installed.
