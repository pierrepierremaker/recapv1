from io import BytesIO
from openai import OpenAI


def transcribe_whisper(client: OpenAI, buffer: BytesIO, language="fr") -> str:
    buffer.seek(0)
    resp = client.audio.transcriptions.create(
        model="whisper-1",
        file=buffer,
        language=language,
    )
    return resp.text
