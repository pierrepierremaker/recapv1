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


def transcribe_diarized(client: OpenAI, buffer: BytesIO):
    buffer.seek(0)

    diarized = client.audio.transcriptions.create(
        model="gpt-4o-transcribe-diarize",
        file=buffer,
        response_format="diarized_json",
    )

    segments = diarized.segments

    lines = []
    for seg in segments:
        speaker = seg.speaker
        text = seg.text
        start = getattr(seg, "start", None)
        end = getattr(seg, "end", None)

        if start is not None:
            lines.append(f"{speaker} [{start:.1f}s–{end:.1f}s] : {text}")
        else:
            lines.append(f"{speaker}: {text}")

    return "\n".join(lines)
