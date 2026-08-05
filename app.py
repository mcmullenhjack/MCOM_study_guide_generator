import streamlit as st
import whisper

from pathlib import Path
import tempfile

# import helper functions
from lecture_transcriber import transcribe_lecture
from pptx_to_pdf_test import pptx_to_pdf
from openai_test import (
    generate_study_guide,
    generate_anki_mastery_plan,
    generate_anki_cards
)

from anki_generator import create_anki_deck

def load_css():
    css = Path("style.css").read_text()
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    

# Basic webpage styling
st.set_page_config(
    page_title="MCOM Study Guide Generator",
    page_icon="assets/mcom_logo.jpg",
    layout="wide"
)

# load our custom CSS styling
load_css()

# Initialize the study guide. When study guide is created, it's stored in cache
if "study_guide" not in st.session_state:
    st.session_state.study_guide = None

# Save its file name as well for easy access
if "study_guide_filename" not in st.session_state:
    st.session_state.study_guide_filename = None

left, center, right = st.columns([1,2,1])
with center:
    st.image(
        "assets/RVU MCOM Program Logo.png",
        width="stretch",
        # width=180
    )
         
st.markdown(
    """
    <h1 class="app-title">
        MCOM Study Guide Generator
    </h1>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="title-divider"></div>
    """,
    unsafe_allow_html=True,
)

# Keep whisper transcription model in cache 
@st.cache_resource
def load_whisper_model():
    return whisper.load_model("base")

# Define function for uploading files to the GPT API instance
def save_uploaded_file(uploaded_file):
    temp_dir = Path(tempfile.gettempdir())
    file_path = temp_dir / uploaded_file.name

    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    return file_path

# Helper function to clear generated study guide so user does not accidentally
# create anki cards from a previously cached study guide.
def clear_generated_outputs():
    st.session_state.study_guide = None
    st.session_state.study_guide_filename = None
    
# combine the transcripts of all uploaded lectures
def combine_transcripts(
    transcript_paths: list[Path],
) -> Path | None:
    if not transcript_paths:
        return None

    combined_sections: list[str] = []

    for index, transcript_path in enumerate(
        transcript_paths,
        start=1,
    ):
        transcript_text = transcript_path.read_text(
            encoding="utf-8",
        ).strip()

        combined_sections.append(
            "\n".join(
                [
                    "=" * 60,
                    f"LECTURE RECORDING {index}",
                    f"SOURCE FILE: {transcript_path.name}",
                    "=" * 60,
                    "",
                    transcript_text,
                ]
            )
        )

    combined_path = (
        Path(tempfile.gettempdir())
        / "combined_lecture_transcript.txt"
    )

    combined_path.write_text(
        "\n\n".join(combined_sections),
        encoding="utf-8",
    )

    return combined_path

# allow user to upload lecture file
with st.container():
    st.markdown(
        """
        <div class="section-header">
            Upload Lecture Recording:
        </div>
        """,
        unsafe_allow_html=True,
    )
    lecture_files = st.file_uploader(
        "Upload Lecture Recordings:",
        type=["mp4", "m4a", "mp3", "wav"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        on_change=clear_generated_outputs,
    )
    # media_path = None

# allow user to upload lecture slides (powerpoint)
# st.markdown("### ")
with st.container():
    st.markdown(
        """
        <div class="section-header">
            Upload Lecture Slides:
        </div>
        """,
        unsafe_allow_html=True,
    )
    slides_file = st.file_uploader(
        "Upload Lecture Slides:",
        type=["pptx", "pdf"],
        label_visibility="collapsed",
        on_change=clear_generated_outputs,
    )
    pptx_path = None

# save them to temp file
media_paths: list[Path] = []

if lecture_files:
    media_paths = [
        save_uploaded_file(lecture_file)
        for lecture_file in lecture_files
    ]
    
if slides_file:
    pptx_path = save_uploaded_file(slides_file)

## create function to clean them up
def clean_learning_objectives(text):
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]
    return "\n".join(lines)

## allow user to copy/paste them
# st.markdown("### ")
with st.container():
    st.markdown(
        """
        <div class="section-header">
            Paste Learning Objectives:
        </div>
        """,
        unsafe_allow_html=True,
    )
    learning_objectives = clean_learning_objectives(
        st.text_area(
            "Paste Learning Objectives:",
            height=250,
            placeholder="""
LO 1: Understand...
LO 2: Explain...
LO 3: Describe...
""",
            label_visibility="collapsed",
            on_change=clear_generated_outputs,
        )
    )

st.markdown("<br>", unsafe_allow_html=True)

generate_study = st.button(
    "Generate Study Guide",
    use_container_width=True
)

generate_anki = st.button(
    "Generate Anki Deck (.apkg)",
    use_container_width=True,
    disabled=st.session_state.study_guide is None,
)

if st.session_state.study_guide is None:
    st.caption("Generate a study guide before creating the Anki deck.")

if generate_study:
    
    if not learning_objectives:
        st.error("Please paste the learning objectives.")
        st.stop()
    
    # initialize the progress box for tracking
    with st.status("Generating Study Guide...", expanded=True) as status:
    
        # transcribe the lecture from uploaded path
        if media_paths:
            st.write("Lecture processing order:")

            for index, path in enumerate(media_paths, start=1):
                st.write(f"{index}. {path.name}")
                
            model = load_whisper_model()
            transcript_paths: list[Path] = []

            for index, media_path in enumerate(
                media_paths,
                start=1,
            ):
                st.write(
                    f"Transcribing lecture recording "
                    f"{index} of {len(media_paths)}..."
                )

                transcript_path = transcribe_lecture(
                    media_path,
                    model,
                )

                transcript_paths.append(
                    Path(transcript_path)
                )
        else:
            transcript_paths = []
            
        transcript_path = combine_transcripts(
            transcript_paths
        )

        # convert user uploaded powerpoint to PDF
        if pptx_path:
            st.write("Converting PowerPoint to PDF...")
            
            if pptx_path.suffix == '.pptx':
                slides_path = pptx_to_pdf(pptx_path)
            else:
                slides_path = pptx_path
        else:
            slides_path = None
            
        # generate study guide. Don't crash app if unsuccessful
        try:
            study_guide = generate_study_guide(
                transcript_path=transcript_path,
                slides_path=slides_path,
                learning_objectives=learning_objectives,
                model="gpt-5.5",
                max_output_tokens=20000
            )
            
            st.session_state.study_guide = study_guide
            
        except Exception as e:
            st.error(f"Study guide generation failed:\n{e}")
            st.stop()

        st.write("Outputting Study Guide...")
        if lecture_files:
            lecture_name = Path(
                lecture_files[0].name
            ).stem
            
        else:
            lecture_name = Path(slides_file.name).stem
            
        auto_output_name = f"{lecture_name} - Study Guide.pdf"
        st.session_state.study_guide_filename = auto_output_name

        # st.download_button(
        #     "Download Study Guide",
        #     data = study_guide.pdf_bytes,
        #     file_name = auto_output_name,
        #     mime = "application/pdf"
        # )
        
        status.update(
            label = "Study Guide Completed!", state = "complete", expanded=True
        )
        
# Render download button separately from the study guide generation
# this way, the PDF download is not lost when clicking another button
if st.session_state.study_guide is not None:
    st.download_button(
        "Download Study Guide",
        data=st.session_state.study_guide.pdf_bytes,
        file_name=st.session_state.study_guide_filename,
        mime="application/pdf",
        use_container_width=True,
    )


#### GENERATE ANKI DECK ####
if generate_anki:

    study_guide = st.session_state.study_guide

    if study_guide is None:
        st.error(
            "Please generate a study guide before creating the Anki deck."
        )
        st.stop()

    with st.status(
        "Generating Anki Deck...",
        expanded=True,
    ) as status:

        st.write("Planning Anki Deck...")

        mastery_plan = generate_anki_mastery_plan(
            study_guide_markdown=study_guide.markdown,
            model="gpt-5.5",
        )

        st.write("Creating Anki Cards...")

        try:
            anki_deck = generate_anki_cards(
                mastery_plan=mastery_plan,
                model="gpt-5.5",
            )
            
            Path("debug_anki_mastery_plan.json").write_text(
                mastery_plan.model_dump_json(indent=2),
                encoding="utf-8",
            )

            Path("debug_anki_deck.json").write_text(
                anki_deck.model_dump_json(indent=2),
                encoding="utf-8",
            )

        except Exception as e:
            status.update(
                label="Anki Deck Generation Failed",
                state="error",
                expanded=True,
            )
            st.error(
                f"Anki card generation failed:\n{e}"
            )
            st.stop()

        st.write("Building Anki Deck...")

        if lecture_file:
            lecture_name = Path(
                lecture_file.name
            ).stem
            
        else:
            lecture_name = Path(
                slides_file.name
            ).stem

        anki_path = create_anki_deck(
            deck_name=lecture_name,
            cards=[
                card.model_dump()
                for card in anki_deck.cards
            ],
        )

        with open(anki_path, "rb") as f:
            anki_bytes = f.read()

        st.download_button(
            "Download Anki Deck",
            data=anki_bytes,
            file_name=f"{lecture_name} - Anki Deck.apkg",
            mime="application/octet-stream",
            use_container_width=True,
        )

        status.update(
            label="Anki Deck Completed!",
            state="complete",
            expanded=True,
        )
