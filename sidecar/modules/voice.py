import os
import json
import tempfile
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

class TTSRequest(BaseModel):
    text: str
    voice: str = "en-US-JennyNeural"

@router.post("/tts")
def text_to_speech(req: TTSRequest):
    try:
        import edge_tts
        import asyncio

        async def _tts():
            communicate = edge_tts.Communicate(req.text, req.voice)
            tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            await communicate.save(tmp.name)
            return tmp.name

        path = asyncio.run(_tts())
        return {"path": path, "format": "mp3", "text": req.text}
    except ImportError:
        raise HTTPException(501, "edge_tts not installed (pip install edge-tts) for TTS")
    except Exception as e:
        raise HTTPException(500, str(e))

@router.get("/voices")
def list_voices():
    return {
        "voices": [
            {"id": "en-US-JennyNeural", "name": "Jenny (English US)", "gender": "Female"},
            {"id": "en-US-GuyNeural", "name": "Guy (English US)", "gender": "Male"},
            {"id": "en-GB-SoniaNeural", "name": "Sonia (English UK)", "gender": "Female"},
            {"id": "es-MX-DaliaNeural", "name": "Dalia (Spanish MX)", "gender": "Female"},
            {"id": "es-ES-AlvaroNeural", "name": "Alvaro (Spanish ES)", "gender": "Male"},
        ]
    }

@router.post("/stt")
def speech_to_text():
    raise HTTPException(501, "STT uses browser Web Speech API. Use frontend SpeechRecognition.")
