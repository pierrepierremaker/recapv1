import streamlit as st


def ui_header():
    st.set_page_config(
        page_title="Compte rendu de réunion",
        page_icon="📝",
        layout="wide",
    )

    st.title("📝 Générateur Premium de Compte Rendu de Réunion")
    st.caption("Transforme n'importe quel fichier audio en transcription + CR structuré.")


def ui_sidebar():
    with st.sidebar:
        st.header("⚙️ Options")
        st.info(
            "Formats acceptés : MP3, WAV, M4A, AAC, AMR\n"
            "Limite : 25 Mo\n"
            "Models : Whisper-1, GPT-4o-Diarize, GPT-4o-mini"
        )
