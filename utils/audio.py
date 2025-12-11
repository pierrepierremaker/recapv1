import subprocess
import tempfile
from io import BytesIO


MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 Mo


def convert_to_wav(input_bytes: bytes, input_extension: str) -> BytesIO:
    """
    Convertit AAC/AMR/M4A/MP3 en WAV via ffmpeg (mono / 16 kHz).
    Retourne un BytesIO compatible Whisper.
    """

    with tempfile.NamedTemporaryFile(suffix=f".{input_extension}", delete=False) as temp_in:
        temp_in.write(input_bytes)
        temp_in.flush()
        input_path = temp_in.name

    output_path = input_path + "_converted.wav"

    command = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-ac", "1",
        "-ar", "16000",
        output_path
    ]

    subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    with open(output_path, "rb") as f:
        wav_data = f.read()

    buffer = BytesIO(wav_data)
    buffer.name = "converted.wav"
    return buffer


def prepare_audio(uploaded_file):
    """
    Gère :
    - taille max
    - conversion AAC/AMR → WAV
    - retour BytesIO prêt pour Whisper
    """

    file_ext = uploaded_file.name.split(".")[-1].lower()
    raw_bytes = uploaded_file.getvalue()

    if uploaded_file.size > MAX_FILE_SIZE:
        raise ValueError(
            f"Fichier trop volumineux ({uploaded_file.size/1024/1024:.2f} Mo). "
            f"Limite actuelle : 25 Mo."
        )

    if file_ext in ["aac", "amr"]:
        return convert_to_wav(raw_bytes, file_ext)

    # sinon fichier standard → on garde tel quel
    buffer = BytesIO(raw_bytes)
    buffer.name = uploaded_file.name
    return buffer
