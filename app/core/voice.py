"""
Sarvam AI Speech & Voice Processing Module.
Supports:
1. Speech-to-Text (STT) via `saaras:v4` (mode="codemix")
2. Text-to-Speech (TTS) via `bulbul:v3` / `bulbul:v4-flash` returning base64 WAV
"""
import base64
import httpx
from typing import Dict, Any, Optional

from app.config import (
    SARVAM_API_KEY,
    SARVAM_BASE_URL
)

LANGUAGE_SPEAKERS = {
    "hi-IN": "priya",
    "kn-IN": "kavya",
    "ta-IN": "vijay",
    "en-IN": "shubh"
}

VALID_BULBUL_SPEAKERS = {
    "aditya", "ritu", "ashutosh", "priya", "neha", "rahul", "pooja", "rohan",
    "simran", "kavya", "amit", "dev", "ishita", "shreya", "ratan", "varun",
    "manan", "sumit", "roopa", "kabir", "aayan", "shubh", "advait", "anand",
    "tanya", "tarun", "sunny", "mani", "gokul", "vijay", "shruti", "suhani",
    "mohit", "kavitha", "rehan", "soham", "rupali"
}

def synthesize_speech(
    text: str,
    language_code: str = "hi-IN",
    speaker: Optional[str] = None
) -> Dict[str, Any]:
    """Calls Sarvam Bulbul TTS and returns playable base64 WAV."""
    candidate_speaker = speaker or LANGUAGE_SPEAKERS.get(language_code, "priya")
    if candidate_speaker not in VALID_BULBUL_SPEAKERS:
        candidate_speaker = LANGUAGE_SPEAKERS.get(language_code, "aditya")
    if candidate_speaker not in VALID_BULBUL_SPEAKERS:
        candidate_speaker = "aditya"

    payload = {
        "inputs": [text[:500]],
        "target_language_code": language_code,
        "speaker": candidate_speaker,
        "pitch": 0,
        "pace": 1.0,
        "loudness": 1.5,
        "speech_sample_rate": 8000,
        "enable_preprocessing": True,
        "model": "bulbul:v3"
    }

    headers = {
        "api-subscription-key": SARVAM_API_KEY,
        "Content-Type": "application/json"
    }

    try:
        with httpx.Client(timeout=25.0) as client:
            res = client.post(f"{SARVAM_BASE_URL}/text-to-speech", json=payload, headers=headers)
            if res.status_code == 200:
                data = res.json()
                audios = data.get("audios", [])
                audio_b64 = audios[0] if audios else ""
                return {
                    "success": True,
                    "audio_base64": audio_b64,
                    "audio_data_uri": f"data:audio/wav;base64,{audio_b64}" if audio_b64 else "",
                    "speaker": candidate_speaker,
                    "language": language_code
                }
            else:
                # Universal fallback speaker: aditya
                if candidate_speaker != "aditya":
                    payload["speaker"] = "aditya"
                    res_retry = client.post(f"{SARVAM_BASE_URL}/text-to-speech", json=payload, headers=headers)
                    if res_retry.status_code == 200:
                        data = res_retry.json()
                        audios = data.get("audios", [])
                        audio_b64 = audios[0] if audios else ""
                        return {
                            "success": True,
                            "audio_base64": audio_b64,
                            "audio_data_uri": f"data:audio/wav;base64,{audio_b64}",
                            "speaker": "aditya",
                            "language": language_code
                        }
                return {
                    "success": False,
                    "error": f"Sarvam TTS HTTP {res.status_code}: {res.text}",
                    "audio_base64": ""
                }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "audio_base64": ""
        }

def transcribe_audio(
    audio_bytes: bytes,
    filename: str = "borrower_reply.wav",
    language_code: str = "hi-IN"
) -> Dict[str, Any]:
    """Transcribes borrower audio using `saaras:v4` in `codemix` mode."""
    headers = {
        "api-subscription-key": SARVAM_API_KEY
    }
    try:
        files = {
            "file": (filename, audio_bytes, "audio/wav")
        }
        data = {
            "model": "saaras:v4",
            "mode": "codemix",
            "language_code": language_code
        }
        with httpx.Client(timeout=30.0) as client:
            res = client.post(f"{SARVAM_BASE_URL}/speech-to-text", files=files, data=data, headers=headers)
            if res.status_code == 200:
                resp_json = res.json()
                return {
                    "success": True,
                    "transcript": resp_json.get("transcript", ""),
                    "language_code": resp_json.get("language_code", language_code)
                }
            else:
                return {
                    "success": False,
                    "error": f"Saaras STT HTTP {res.status_code}: {res.text}",
                    "transcript": ""
                }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "transcript": ""
        }

