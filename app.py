import os
from io import BytesIO
from typing import List

import streamlit as st
from dotenv import load_dotenv
from pydub import AudioSegment
from openai import OpenAI

# -----------------------
# 1. Chargement des variables d'environnement
# -----------------------
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    client = None
else:
    client = OpenAI(api_key=api_key)

# -----------------------
# 2. Configuration de la page Streamlit
# -----------------------
st.set_page_config(
    page_title="Compte rendu de réunion automatique",
    page_icon="📝",
    layout="centered",
)

st.caption(f"📦 Taille max upload côté Streamlit : {st.get_option('server.maxUploadSize')} Mo")

st.title("📝 Générateur de compte rendu de réunion")
st.write(
    "Dépose un fichier audio de réunion (MP3 / WAV) et l’outil générera d’abord une transcription complète, "
    "puis un compte rendu structuré (dans les prochaines étapes)."
)

# -----------------------
# 3. Upload du fichier audio
# -----------------------
uploaded_file = st.file_uploader(
    "Dépose ton fichier audio ici",
    type=["mp3", "wav", "m4a"],
    help="Formats supportés : MP3, WAV, M4A",
)

status_placeholder = st.empty()

# -----------------------
# 4. Fonctions utilitaires
# -----------------------
def load_audio_to_pydub(file) -> AudioSegment:
    """Charge le fichier uploadé dans un objet AudioSegment (pydub)."""
    data = BytesIO(file.read())
    audio = AudioSegment.from_file(data)
    # On force en mono & 16 kHz pour plus de stabilité
    audio = audio.set_channels(1).set_frame_rate(16000)
    return audio


def split_audio(audio: AudioSegment, max_chunk_ms: int = 10 * 60 * 1000) -> List[AudioSegment]:
    """
    Découpe l'audio en morceaux (chunks) de durée maximale max_chunk_ms (par défaut 10 minutes).
    Retourne une liste d'AudioSegment.
    """
    chunks = []
    total_length = len(audio)
    for start_ms in range(0, total_length, max_chunk_ms):
        end_ms = min(start_ms + max_chunk_ms, total_length)
        chunk = audio[start_ms:end_ms]
        chunks.append(chunk)
    return chunks


def estimate_whisper_cost(duration_minutes: float, price_per_minute_usd: float = 0.006) -> float:
    """
    Estime le coût de transcription Whisper (whisper-1) en dollars.
    Par défaut : 0,006 $ / minute (à ajuster si besoin).
    """
    return duration_minutes * price_per_minute_usd


def transcribe_chunk_with_whisper(chunk: AudioSegment, language: str = "fr") -> str:
    """
    Transcrit un chunk d'audio avec Whisper (whisper-1) et renvoie le texte.
    """
    if client is None:
        raise RuntimeError("Client OpenAI non initialisé (clé API manquante).")

    # On exporte le chunk vers un buffer en mémoire, en WAV (format très compatible)
    buffer = BytesIO()
    chunk.export(buffer, format="wav")
    buffer.seek(0)
    buffer.name = "chunk.wav"  # important pour que l'API reconnaisse le format

    transcription = client.audio.transcriptions.create(
        model="whisper-1",
        file=buffer,
        language=language,
    )
    return transcription.text


# -----------------------
# 5. Interface principale
# -----------------------
if uploaded_file is not None:
    st.success(f"✅ Fichier chargé : **{uploaded_file.name}**")
    st.write("Tu peux maintenant lancer la transcription audio → texte.")

    # --------- 5.A – Mode classique : Whisper + découpage ---------
    st.markdown("### 🎧 Transcription classique (Whisper + découpage)")

    # Slider pour régler la durée max d'un chunk (optionnel)
    chunk_length_minutes = st.slider(
        "Durée maximale par morceau (chunk) pour la transcription",
        min_value=5,
        max_value=20,
        value=10,
        step=5,
        help="Cela permet de gérer de longues réunions sans dépasser les limites de l'API.",
    )

    if st.button("Transcrire la réunion (Whisper)"):
        if client is None:
            st.error("❌ Aucune clé API OpenAI détectée. Configure OPENAI_API_KEY pour continuer.")
        else:
            try:
                # 1) Chargement de l'audio
                status_placeholder.info("⏳ Chargement de l'audio...")
                audio = load_audio_to_pydub(uploaded_file)

                duration_seconds = len(audio) / 1000
                duration_minutes = duration_seconds / 60
                st.write(f"🕒 Durée estimée de l'audio : **{duration_minutes:.1f} minutes**")

                # Estimation du coût
                estimated_cost = estimate_whisper_cost(duration_minutes)
                st.write(f"💰 Coût estimé de la transcription (whisper-1) : ~**{estimated_cost:.4f} $**")

                # 2) Découpage en chunks
                status_placeholder.info("✂️ Découpage de l'audio en morceaux...")
                max_chunk_ms = chunk_length_minutes * 60 * 1000
                chunks = split_audio(audio, max_chunk_ms=max_chunk_ms)
                st.write(f"🔹 Nombre de morceaux : **{len(chunks)}**")

                # 3) Transcription chunk par chunk
                status_placeholder.info("🗣️ Transcription en cours avec Whisper...")

                all_text_parts = []
                progress_bar = st.progress(0)
                total_chunks = len(chunks)

                for idx, chunk in enumerate(chunks, start=1):
                    status_placeholder.info(f"🗣️ Transcription du morceau {idx}/{total_chunks}...")
                    text = transcribe_chunk_with_whisper(chunk, language="fr")
                    all_text_parts.append(text)

                    progress_bar.progress(idx / total_chunks)

                full_transcript = "\n\n".join(all_text_parts)

                status_placeholder.success("✅ Transcription terminée !")

                # 4) Affichage de la transcription
                st.subheader("🧾 Transcription complète")
                st.write(
                    "Voici la transcription brute de la réunion. "
                    "La prochaine étape consistera à générer un compte rendu structuré à partir de ce texte."
                )
                st.text_area(
                    "Transcription",
                    value=full_transcript,
                    height=400,
                )

                # On garde dans la session pour utilisation future (résumé, CR, etc.)
                st.session_state["full_transcript"] = full_transcript

            except Exception as e:
                status_placeholder.error("❌ Erreur lors de la transcription.")
                st.error(str(e))

    # --------- 5.B – Mode diarisation : gpt-4o-transcribe-diarize ---------
    st.markdown("### 🔊 Transcription avec identification des locuteurs")

    st.write(
        "Utilise ce mode si ton fichier fait **25 Mo ou moins**. "
        "Le modèle `gpt-4o-transcribe-diarize` ajoutera des labels de locuteurs (A, B, C...)."
    )

    if st.button("Transcrire avec diarisation (gpt-4o-transcribe-diarize)"):
        if client is None:
            st.error("❌ Aucune clé API OpenAI détectée. Configure OPENAI_API_KEY pour continuer.")
        else:
            # 25 Mo = 25 * 1024 * 1024 octets
            max_bytes = 25 * 1024 * 1024
            if uploaded_file.size > max_bytes:
                st.error(
                    f"❌ Fichier trop volumineux pour la diarisation (taille : {uploaded_file.size/1024/1024:.1f} Mo). "
                    "La limite de l'API est 25 Mo. Utilise plutôt la transcription 'Whisper' avec découpage."
                )
            else:
                try:
                    with st.spinner("🧠 Transcription + diarisation en cours..."):
                        # On récupère les bytes du fichier uploadé
                        audio_bytes = uploaded_file.getvalue()
                        buffer = BytesIO(audio_bytes)
                        # Donner un nom avec une extension reconnue
                        buffer.name = uploaded_file.name or "audio.wav"

                        diarized = client.audio.transcriptions.create(
                            model="gpt-4o-transcribe-diarize",
                            file=buffer,
                            response_format="diarized_json",
                            chunking_strategy="auto",
                        )

                        # diarized.segments contient les segments avec speaker / start / end / text
                        segments = diarized.segments

                        # On construit un texte lisible du type :
                        # Speaker A [0.0s–5.2s] : blabla
                        lines = []
                        for seg in segments:
                            speaker = seg.speaker
                            start = getattr(seg, "start", None)
                            end = getattr(seg, "end", None)
                            text = seg.text

                            if start is not None and end is not None:
                                lines.append(
                                    f"Speaker {speaker} [{start:.1f}s–{end:.1f}s] : {text}"
                                )
                            else:
                                lines.append(f"Speaker {speaker} : {text}")

                        labeled_transcript = "\n".join(lines)

                        st.success("✅ Transcription diarisée terminée !")
                        st.subheader("🧾 Transcription avec locuteurs")
                        st.text_area(
                            "Texte diarisé (qui parle, quand, quoi)",
                            value=labeled_transcript,
                            height=400,
                        )

                        # On garde ça dans la session pour le futur compte rendu
                        st.session_state["full_transcript"] = labeled_transcript

                except Exception as e:
                    st.error("❌ Erreur lors de la transcription avec diarisation.")
                    st.error(str(e))

else:
    st.info("⤴️ Commence par déposer un fichier audio pour continuer.")

# -----------------------
# 6. Génération du compte rendu avec GPT-4o-mini
# -----------------------
st.markdown("---")
st.subheader("🧠 Générer un compte rendu de la réunion")

if "full_transcript" not in st.session_state:
    st.info("➡️ Transcris d'abord une réunion (avec ou sans diarisation) pour pouvoir générer un compte rendu.")
else:
    transcript_text = st.session_state["full_transcript"]

    st.write(
        "À partir de la transcription ci-dessus, l’outil va produire un compte rendu synthétique, "
        "structuré par thèmes et par intervenant."
    )

    # Optionnel : rappel de la transcription (extrait)
    with st.expander("Voir un extrait de la transcription utilisée"):
        st.text_area(
            "Transcription (extrait)",
            value=transcript_text[:2000] + ("..." if len(transcript_text) > 2000 else ""),
            height=200,
        )

    style = st.selectbox(
        "Style de compte rendu",
        ["Professionnel / neutre", "Bullet points synthétiques", "Version détaillée (procès-verbal)"],
        index=0,
    )

    if st.button("✨ Générer le compte rendu"):
        if client is None:
            st.error("❌ Aucune clé API OpenAI détectée. Configure OPENAI_API_KEY pour continuer.")
        else:
            try:
                with st.spinner("🧠 Rédaction du compte rendu en cours..."):
                    # On adapte un peu le ton selon le style choisi
                    if style == "Professionnel / neutre":
                        style_instruction = (
                            "Rédige un compte rendu professionnel, neutre, bien structuré, en français, "
                            "avec des titres et sous-titres clairs."
                        )
                    elif style == "Bullet points synthétiques":
                        style_instruction = (
                            "Fais un résumé très synthétique sous forme de listes à puces, en français, "
                            "en mettant surtout en avant les idées clés et les chiffres importants."
                        )
                    else:  # Version détaillée (procès-verbal)
                        style_instruction = (
                            "Rédige un compte rendu détaillé, proche d'un procès-verbal, en français, "
                            "en respectant fidèlement le contenu sans inventer de faits."
                        )

                    system_msg = (
                        "Tu es un assistant chargé de rédiger des comptes rendus de réunions à partir de transcriptions. "
                        "Tu dois être clair, structuré, fidèle au contenu, et ne pas inventer de décisions ou de chiffres. "
                        "Lorsque la transcription contient des étiquettes de locuteur comme 'Speaker A' ou 'Speaker B', "
                        "explique dans le compte rendu qui semble être qui (ex : intervieweur, invité, expert...), "
                        "sans inventer d'identité réelle."
                    )

                    user_prompt = (
                        f"{style_instruction}\n\n"
                        "Voici la transcription de l'échange (avec éventuellement des labels de locuteurs) :\n\n"
                        f"{transcript_text}\n\n"
                        "Produit maintenant le compte rendu demandé."
                    )

                    resp = client.responses.create(
                        model="gpt-4o-mini",
                        input=[
                            {"role": "system", "content": system_msg},
                            {"role": "user", "content": user_prompt},
                        ],
                    )

                    cr_texte = resp.output[0].content[0].text

                st.subheader("📄 Compte rendu généré")
                st.write(cr_texte)

                # Option : on stocke le CR dans la session pour réutilisation ultérieure (export, etc.)
                st.session_state["meeting_summary"] = cr_texte

            except Exception as e:
                st.error("❌ Erreur lors de la génération du compte rendu.")
                st.error(str(e))
