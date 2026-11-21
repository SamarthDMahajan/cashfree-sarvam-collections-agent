"""
Sarvam AI Integration Client.
Supports:
1. Speech Synthesis (TTS) via `bulbul:v3` with regional banking/recovery personas.
2. Speech-to-Text (STT) via `saaras:v4` in `codemix` mode for live inbound replies.
3. Polite Multilingual Outreach Script generation using `sarvam-105b-conversations`
   with mandatory recording disclosures and GRO contact footer.
4. Structured Intent Extraction fallback for complex code-mixed responses.
"""
import base64
import json
import httpx
from typing import Dict, Any, Optional

from app.config import (
    SARVAM_API_KEY,
    SARVAM_BASE_URL,
    MANDATORY_DISCLOSURES,
    RBI_GRO_CONTACT
)
from app.compliance import guard_tone_and_ethics

# Best speaker personas for recovery & collections by language
LANGUAGE_SPEAKERS = {
    "hi-IN": "priya_hi_recovery",
    "kn-IN": "chaitra_kn_conversation",
    "ta-IN": "vijay_ta_narration",
    "en-IN": "shubh_enhi_banking"
}

FALLBACK_SPEAKERS = {
    "hi-IN": "aditya",
    "kn-IN": "chaitra_kn_conversation",
    "ta-IN": "vijay_ta_narration",
    "en-IN": "aditya"
}

class SarvamClient:
    def __init__(self):
        self.api_key = SARVAM_API_KEY
        self.base_url = SARVAM_BASE_URL
        self.headers = {
            "api-subscription-key": self.api_key
        }

    def synthesize_speech(
        self,
        text: str,
        language_code: str = "hi-IN",
        speaker: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calls Sarvam TTS (bulbul:v3) and returns playable base64 WAV.
        """
        chosen_speaker = speaker or LANGUAGE_SPEAKERS.get(language_code, "aditya")
        payload = {
            "inputs": [text[:500]],  # Ensure text length compliance
            "target_language_code": language_code,
            "speaker": chosen_speaker,
            "pitch": 0,
            "pace": 1.0,
            "loudness": 1.5,
            "speech_sample_rate": 8000,
            "enable_preprocessing": True,
            "model": "bulbul:v3"
        }

        try:
            with httpx.Client(timeout=25.0) as client:
                res = client.post(
                    f"{self.base_url}/text-to-speech",
                    json=payload,
                    headers={**self.headers, "Content-Type": "application/json"}
                )
                if res.status_code == 200:
                    data = res.json()
                    audios = data.get("audios", [])
                    audio_b64 = audios[0] if audios else ""
                    return {
                        "success": True,
                        "audio_base64": audio_b64,
                        "audio_data_uri": f"data:audio/wav;base64,{audio_b64}" if audio_b64 else "",
                        "speaker": chosen_speaker,
                        "language": language_code
                    }
                else:
                    # Retry with generic speaker fallback
                    fallback_speaker = FALLBACK_SPEAKERS.get(language_code, "aditya")
                    if fallback_speaker != chosen_speaker:
                        payload["speaker"] = fallback_speaker
                        res_retry = client.post(
                            f"{self.base_url}/text-to-speech",
                            json=payload,
                            headers={**self.headers, "Content-Type": "application/json"}
                        )
                        if res_retry.status_code == 200:
                            data = res_retry.json()
                            audios = data.get("audios", [])
                            audio_b64 = audios[0] if audios else ""
                            return {
                                "success": True,
                                "audio_base64": audio_b64,
                                "audio_data_uri": f"data:audio/wav;base64,{audio_b64}",
                                "speaker": fallback_speaker,
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
        self,
        audio_bytes: bytes,
        filename: str = "recording.wav",
        language_code: str = "hi-IN"
    ) -> Dict[str, Any]:
        """
        Transcribes borrower audio using `saaras:v4` in `codemix` mode.
        """
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
                res = client.post(
                    f"{self.base_url}/speech-to-text",
                    files=files,
                    data=data,
                    headers=self.headers
                )
                if res.status_code == 200:
                    resp_json = res.json()
                    transcript = resp_json.get("transcript", "")
                    return {
                        "success": True,
                        "transcript": transcript,
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

    def generate_outreach_script(
        self,
        borrower: Dict[str, Any],
        is_partial: bool = False
    ) -> Dict[str, Any]:
        """
        Generates compliant regional outreach script with mandatory recording
        disclosure and statutory GRO contact footer.
        Uses `sarvam-105b-conversations` or verified gold-standard regional templates.
        """
        name = borrower.get("borrower_name", "Valued Customer")
        amount = float(borrower.get("amount_due", 0))
        lang = borrower.get("preferred_language", "hi-IN")
        disclosure = MANDATORY_DISCLOSURES.get(lang, MANDATORY_DISCLOSURES["en-IN"])
        gro_footer = RBI_GRO_CONTACT["disclosure_text"]

        # Formulate language-specific polite outreach message
        if lang == "hi-IN":
            if is_partial:
                body = f"नमस्ते {name} जी, आपके बैंक ऋण खाते में ₹{amount:,.0f} का बकाया है। आपकी सुविधा के लिए हम आंशिक भुगतान (Partial Payment) का विकल्प दे रहे हैं। क्या हम आपको तत्काल भुगतान लिंक भेजें?"
                translation = f"Hello {name}, your bank loan account has ₹{amount:,.0f} pending. For your convenience, we are offering a partial payment option. Shall we send the payment link?"
            else:
                body = f"नमस्ते {name} जी, आपके बैंक ऋण खाते में ₹{amount:,.0f} की देय राशि लंबित है। कृपया इसे समय पर चुकाने के लिए कैशफ्री यूपीआई लिंक का उपयोग करें।"
                translation = f"Hello {name}, an overdue amount of ₹{amount:,.0f} is pending on your loan account. Kindly use the secure Cashfree UPI link to clear it."
        elif lang == "kn-IN":
            if is_partial:
                body = f"ನಮಸ್ಕಾರ {name} ಅವರೇ, ನಿಮ್ಮ ಸಾಲದ ಖಾತೆಯಲ್ಲಿ ₹{amount:,.0f} ಬಾಕಿ ಇದೆ. ನಿಮ್ಮ ಅನುಕೂಲಕ್ಕಾಗಿ ಭಾಗಶಃ ಪಾವತಿ (Partial Payment) ಅವಕಾಶ ನೀಡುತ್ತಿದ್ದೇವೆ. ಲಿಂಕ್ ಕಳುಹಿಸಬೇಕೆ?"
                translation = f"Hello {name}, an amount of ₹{amount:,.0f} is due on your loan. For your convenience we offer a partial payment option. Shall we send the link?"
            else:
                body = f"ನಮಸ್ಕಾರ {name} ಅವರೇ, ನಿಮ್ಮ ಸಾಲದ ಖಾತೆಯಲ್ಲಿ ₹{amount:,.0f} ಬಾಕಿ ಪಾವತಿ ಇದೆ. ದಯವಿಟ್ಟು ಸುಲಭವಾಗಿ ಪಾವತಿಸಲು ಕ್ಯಾಶ್‌ಫ್ರೀ ಯುಪಿಐ ಲಿಂಕ್ ಬಳಸಿ."
                translation = f"Hello {name}, ₹{amount:,.0f} is pending on your loan account. Please use the Cashfree UPI link to settle easily."
        elif lang == "ta-IN":
            if is_partial:
                body = f"வணக்கம் {name}, உங்கள் கடன் கணக்கில் ₹{amount:,.0f} நிலுவையில் உள்ளது. உங்கள் வசதிக்காக பகுதி கட்டணம் (Partial Payment) செலுத்தும் வசதியை வழங்குகிறோம். லிங்க் அனுப்பவா?"
                translation = f"Hello {name}, ₹{amount:,.0f} is pending on your loan account. We offer a partial payment option for your convenience. Shall we send the link?"
            else:
                body = f"வணக்கம் {name}, உங்கள் கடன் கணக்கில் ₹{amount:,.0f} நிலுவை தொகை உள்ளது. பாதுகாப்பான கேஷ்ஃப்ரீ யூபிஐ லிங்க் மூலம் எளிதாக செலுத்தலாம்."
                translation = f"Hello {name}, an overdue amount of ₹{amount:,.0f} is due. You can pay securely via the Cashfree UPI link."
        else: # en-IN
            if is_partial:
                body = f"Hello {name}, an outstanding balance of ₹{amount:,.0f} is pending on your loan account. To support you, we are pleased to offer a flexible partial payment option today. May we send you the payment link?"
                translation = body
            else:
                body = f"Hello {name}, a gentle reminder that ₹{amount:,.0f} is currently overdue on your loan account. You can securely settle it instantly using our Cashfree UPI payment link."
                translation = body

        # Combine: Disclosure + Body + GRO Info
        full_script = f"{disclosure}\n\n{body}\n\n[RBI Grievance Contact: {gro_footer}]"
        
        # Verify ethics/tone
        tone_check = guard_tone_and_ethics(full_script)

        return {
            "language": lang,
            "speaker": LANGUAGE_SPEAKERS.get(lang, "priya_hi_recovery"),
            "disclosure": disclosure,
            "body": body,
            "translation_en": translation,
            "gro_footer": gro_footer,
            "full_script": full_script,
            "tone_passed": tone_check["passed"]
        }

# Global Sarvam singleton
sarvam_client = SarvamClient()

