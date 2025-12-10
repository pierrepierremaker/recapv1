import os
from io import BytesIO
from typing import List, Union
# from pydub import AudioSegment  <--- COMMENTÉ POUR ÉVITER L'ERREUR pyaudioop
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
from openai.types.audio import Transcription

# --- NOUVELLE CONSTANTE POUR LA LIMITE DE TAILLE (API WHISPER) ---
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 Mo en bytes

# -----------------------
# 1. Chargement des variables d'environnement
# -----------------------
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    client = None
else:
    # Utilisation d'un client OpenAI standard
    # Remarque : si vous utilisez l'API Gemini, remplacez OpenAI par gemini.Client
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
st.warning(
    "⚠️ **Correction d'erreur `pyaudioop` :** Le découpage audio automatique pour les fichiers de "
    "plus de 25 Mo est temporairement désactivé. Veuillez n'uploader que des fichiers de **25 Mo maximum** "
    "jusqu'à la prochaine mise à jour."
)

# -----------------------
# 3. Upload du fichier audio
# -----------------------
uploaded_file = st.file_uploader(
    "Dépose ton fichier audio ici (MP3 / WAV / M4A) - **MAX 25 Mo**",
    type=["mp3", "wav", "m4a"],
    help="Formats supportés : MP3, WAV, M4A",
)

status_placeholder = st.empty()


# -----------------------
# 4. Fonctions utilitaires (SANS pydub)
# -----------------------

def transcribe_audio_simple(audio_file: BytesIO, language: str = "fr") -> str:
    """
    Transcrit un fichier audio unique (moins de 25 Mo) avec Whisper.
    L'objet doit être un BytesIO (mémoire) avec le nom de fichier correct.
    """
    if client is None:
        raise RuntimeError("Client OpenAI non initialisé (clé API manquante).")

    # On s'assure que le pointeur est au début pour l'API
    audio_file.seek(0)
    
    # L'API Whisper attend un objet de type fichier
    transcription: Transcription = client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        language=language,
    )
    return transcription.text


def estimate_whisper_cost(duration_minutes: float, price_per_minute_usd: float = 0.006) -> float:
    """
    Estime le coût de transcription Whisper (whisper-1) en dollars.
    (La durée doit être estimée manuellement si pydub n'est pas utilisé)
    """
    return duration_minutes * price_per_minute_usd


# -----------------------
# 5. Interface principale
# -----------------------
if uploaded_file is not None:
    st.success(f"✅ Fichier chargé : **{uploaded_file.name}**")
    
    # On convertit le fichier uploadé en objet BytesIO pour l'API
    audio_buffer = BytesIO(uploaded_file.getvalue())
    # On réassigne le nom pour que l'API reconnaisse le format
    audio_buffer.name = uploaded_file.name or "audio_file.mp3"
    
    # Vérification simple de la taille
    file_size_mb = uploaded_file.size / (1024 * 1024)
    
    if uploaded_file.size > MAX_FILE_SIZE:
        st.error(
            f"❌ Fichier trop volumineux ({file_size_mb:.2f} Mo). "
            "La limite actuelle pour ce mode de transcription est 25 Mo."
        )
    else:
        st.write("Tu peux maintenant lancer la transcription audio → texte.")
        
        # --------- 5.A – Mode classique : Whisper (sans découpage) ---------
        st.markdown("### 🎧 Transcription simple (Fichier unique)")
        
        # Pour le mode simple, on demande à l'utilisateur d'estimer la durée pour le coût
        duration_minutes = st.number_input(
            "Durée de la réunion estimée (minutes)", 
            min_value=1.0, 
            value=min(file_size_mb * 2.5, 60.0), # Estimation grossière
            step=5.0,
            help="Entre la durée pour estimer le coût (API Whisper : 0,006 $ / minute).",
        )
        
        estimated_cost = estimate_whisper_cost(duration_minutes)
        st.write(f"💰 Coût estimé de la transcription : ~**{estimated_cost:.4f} $**")
        
        if st.button("Transcrire la réunion (Whisper)"):
            if client is None:
                st.error("❌ Aucune clé API OpenAI détectée. Configure OPENAI_API_KEY pour continuer.")
            else:
                try:
                    status_placeholder.info("🗣️ Transcription en cours avec Whisper...")
                    
                    # 1) Transcription
                    full_transcript = transcribe_audio_simple(audio_buffer, language="fr")

                    status_placeholder.success("✅ Transcription terminée !")

                    # 2) Affichage de la transcription
                    st.subheader("🧾 Transcription complète")
                    st.write(
                        "Voici la transcription brute de la réunion. "
                        "La prochaine étape (en bas) est la génération du compte rendu structuré."
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
                    st.error(f"Une erreur est survenue lors de l'appel à l'API Whisper : {str(e)}")


    # --------- 5.B – Mode diarisation : gpt-4o-transcribe-diarize ---------
    # Le mode diarisation est naturellement limité à 25 Mo, mais utilise un modèle différent (gpt-4o-transcribe-diarize)
    st.markdown("### 🔊 Transcription avec identification des locuteurs (Diarisation)")

    st.write(
        "Utilise ce mode si ton fichier fait **25 Mo ou moins**. "
        "Le modèle `gpt-4o-transcribe-diarize` est souvent plus performant pour identifier les locuteurs (A, B, C...)."
    )

    if st.button("Transcrire avec diarisation"):
        if client is None:
            st.error("❌ Aucune clé API OpenAI détectée. Configure OPENAI_API_KEY pour continuer.")
        else:
            if uploaded_file.size > MAX_FILE_SIZE:
                st.error(
                    f"❌ Fichier trop volumineux pour la diarisation (taille : {file_size_mb:.1f} Mo). "
                    "La limite de l'API est 25 Mo. Utilise le mode simple si tu peux réduire la taille du fichier."
                )
            else:
                try:
                    with st.spinner("🧠 Transcription + diarisation en cours..."):
                        # Le buffer est déjà créé avec le contenu du fichier et le nom
                        
                        diarized = client.audio.transcriptions.create(
                            model="gpt-4o-transcribe-diarize",
                            file=audio_buffer,
                            response_format="diarized_json",
                            # chunking_strategy="auto", # Non nécessaire pour gpt-4o-transcribe-diarize, il le gère
                        )

                        # diarized.segments contient les segments avec speaker / start / end / text
                        segments = diarized.segments

                        # On construit un texte lisible
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
                    st.error(f"Une erreur est survenue lors de l'appel à l'API : {str(e)}")

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

                    # --- APPEL À L'API DE RÉSUMÉ ---
                    # Nous allons utiliser client.chat.completions.create qui est la méthode standard pour GPT
                    # L'API Gemini que vous utilisiez (client.responses.create) n'est pas standard pour OpenAI.
                    resp = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": system_msg},
                            {"role": "user", "content": user_prompt},
                        ],
                    )

                    # Le format de réponse standard pour OpenAI Chat API
                    cr_texte = resp.choices[0].message.content 

                st.subheader("📄 Compte rendu généré")
                st.write(cr_texte)

                # Option : on stocke le CR dans la session pour réutilisation ultérieure (export, etc.)
                st.session_state["meeting_summary"] = cr_texte
                
                st.download_button(
                    label="Télécharger le compte rendu (Markdown)",
                    data=cr_texte,
                    file_name=f"compte_rendu_{uploaded_file.name.split('.')[0]}_CR.md",
                    mime="text/markdown"
                )

            except Exception as e:
                st.error("❌ Erreur lors de la génération du compte rendu.")
                st.error(f"Une erreur est survenue lors de l'appel à l'API GPT-4o-mini : {str(e)}")