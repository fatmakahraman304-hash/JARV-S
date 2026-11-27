"""Bounded, completed PCM reply encoding. No disk or shared history."""
import base64
import io
import wave

MAX_REPLY_BYTES = 30 * 24000 * 2


def reply_message(pcm):
    if not isinstance(pcm, bytes) or not 0 < len(pcm) <= MAX_REPLY_BYTES or len(pcm) % 2:
        raise ValueError("Invalid phone reply PCM")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(pcm)
    return {"type": "realtime_phone_reply",
            "wav": base64.b64encode(buffer.getvalue()).decode("ascii")}
