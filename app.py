import os
import datetime
from io import BytesIO

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

from utils.ui import ui_header, ui_sidebar
from utils.audio import prepare_audio
from utils.transcription import transcribe_whisper, transcribe_diarized
from utils.export import export_docx, export_pdf

# Chargement .env et client OpenAI
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key) if api_key else None

# 🎨 UI générale
ui_header()
ui_sidebar()

# -----------------------
# 1. Formulaire métadonnées réunion
# -----------------------
st.subheader("🧾 Informations sur la réunion")

# Initialisation dans la session
if "meta" not in st.session_state:
    st.session_state["meta"] = {
        "title": "",
        "date": str(datetime.date.today()),
        "location": "",
        "participants": "",
    }

meta = st.session_state["meta"]

col1, col2 = st.columns(2)
with col1:
    title = st.text_input("Titre de la réunion", value=meta.get("title", ""))
with col2:
    # On stocke la date comme string dans la session pour simplifier la sérialisation
    default_date = datetime.date.fromisoformat(meta.get("date")) if meta.get("date") else datetime.date.today()
    meeting_date = st.date_input("Date", value=default_date)

location = st.text_input("Lieu", value=meta.get("location", ""))
participants = st.text_area(
    "Participants",
    value=meta.get("participants", ""),
    help="Liste des participants (séparés par des virgules ou des retours à la ligne).",
)

# Mise à jour session
st.session_state["meta"] = {
    "title": title.strip(),
    "date": meeting_date.isoformat(),
    "location": location.strip(),
    "participants": participants.strip(),
}

meta = st.session_state["meta"]  # re-récupéré à jour

st.markdown("---")

# -----------------------
# 2. Upload et transcription audio
# -----------------------
st.subheader("⬆️ Importer un fichier audio")

uploaded_file = st.file_uploader(
    "Choisis un fichier (MP3 / WAV / M4A / AAC / AMR)",
    type=["mp3", "wav", "m4a", "aac", "amr"],
)

if uploaded_file and not client:
    st.error("❌ Aucune clé OPENAI_API_KEY détectée dans ton .env")

if uploaded_file and client:
    try:
        audio_buffer = prepare_audio(uploaded_file)
        st.success("✅ Fichier prêt pour transcription")

        mode = st.radio(
            "Mode de transcription",
            ["Whisper (simple)", "Diarisation (locuteurs)"],
            horizontal=True,
        )

        if st.button("🎧 Lancer la transcription"):
            with st.spinner("Transcription en cours…"):
                if mode == "Whisper (simple)":
                    transcript = transcribe_whisper(client, audio_buffer)
                else:
                    transcript = transcribe_diarized(client, audio_buffer)

            st.success("✅ Transcription terminée !")
            st.session_state["transcript"] = transcript

            st.text_area("🧾 Transcription", transcript, height=300)

    except Exception as e:
        st.error(f"❌ Erreur lors de la préparation ou de la transcription : {e}")

elif not uploaded_file:
    st.info("⤴️ Dépose un fichier audio pour commencer.")

st.markdown("---")

# -----------------------
# 3. Génération du compte rendu
# -----------------------
st.subheader("🧠 Générer le compte rendu")

if "transcript" not in st.session_state:
    st.info("➡️ Transcris d'abord une réunion pour pouvoir générer un compte rendu.")
else:
    style = st.selectbox(
        "Style de compte rendu",
        ["Professionnel", "Bullet Points", "Procès-verbal"],
    )

    if st.button("✨ Générer le compte rendu"):
        transcript = st.session_state["transcript"]

        with st.spinner("Rédaction du compte rendu…"):
            system_msg = (
                "Tu es un assistant spécialisé dans la rédaction de comptes rendus de réunion. "
                "Tu dois être clair, structuré, factuel et ne pas inventer de décisions, de chiffres, "
                "ni de participants qui ne figurent pas dans les informations fournies."
            )

            style_instructions = {
                "Professionnel": "Rédige un compte rendu clair, structuré, professionnel, avec des titres et sous-titres.",
                "Bullet Points": "Rédige un résumé synthétique en listes à puces, axé sur les décisions, actions et points clés.",
                "Procès-verbal": "Rédige un procès-verbal détaillé, chronologique, fidèle au contenu.",
            }

            # Construction d’un bloc texte avec les métadonnées
            meta_block = (
                f"Titre de la réunion : {meta.get('title') or 'Non précisé'}\n"
                f"Date : {meta.get('date') or 'Non précisé'}\n"
                f"Lieu : {meta.get('location') or 'Non précisé'}\n"
                f"Participants : {meta.get('participants') or 'Non précisé'}\n"
            )

            user_msg = (
                f"{style_instructions[style]}\n\n"
                "Voici les informations contextuelles sur la réunion :\n"
                f"{meta_block}\n\n"
                "Voici maintenant la transcription de la réunion. "
                "Utilise les informations de contexte pour compléter les champs "
                "comme la date, les participants, etc., sans laisser de champs vides :\n\n"
                f"{transcript}"
            )

            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
            )

            summary = resp.choices[0].message.content
            st.session_state["summary"] = summary

        st.subheader("📄 Compte rendu généré")
        st.write(summary)

        st.markdown("### 📥 Export")

        # Exports avec métadonnées
        docx_file = export_docx(summary, meta)
        st.download_button(
            "📄 Télécharger en DOCX",
            data=docx_file,
            file_name="compte_rendu_reunion.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

        pdf_file = export_pdf(summary, meta)
        st.download_button(
            "📕 Télécharger en PDF",
            data=pdf_file,
            file_name="compte_rendu_reunion.pdf",
            mime="application/pdf",
        )
