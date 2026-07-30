import streamlit as st
import whisper

from pathlib import Path
import tempfile

# import helper functions
from lecture_transcriber import transcribe_lecture
from pptx_to_pdf_test import pptx_to_pdf
from openai_test import generate_study_guide

def load_css():
    css = Path("style.css").read_text()
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    

# Basic webpage styling
st.set_page_config(
    page_title="MCOM Study Guide Generator",
    page_icon="assets/mcom_logo.jpg",
    layout="wide"
)

load_css()

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

# allow user to upload lecture file
with st.container():
    st.markdown(
        """
        <div class="section-header">
            Upload Lecture Recording
        </div>
        """,
        unsafe_allow_html=True,
    )
    lecture_file = st.file_uploader(
        "Upload Lecture Recording:",
        type=["mp4", "m4a", "mp3", "wav"],
        label_visibility="collapsed"
    )

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
        type=["pptx"],
        label_visibility="collapsed"
    )

# save them to temp file
if lecture_file:
    media_path = save_uploaded_file(lecture_file)
    
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
        label_visibility="collapsed"
        )
    )

st.markdown("<br>", unsafe_allow_html=True)

generate = st.button(
    "Generate & Download Study Guide",
    use_container_width=True
)

if generate:
    
    # ensure user uploaded all the necessary files/info. If not, end
    if not lecture_file:
        st.error("Please upload a lecture recording.")
        st.stop()

    if not slides_file:
        st.error("Please upload the lecture slides.")
        st.stop()

    if not learning_objectives:
        st.error("Please paste the learning objectives.")
        st.stop()
    
    # initialize the progress box for tracking
    with st.status("Generating Study Guide...", expanded=True) as status:
    
        # transcribe the lecture from uploaded path
        st.write("Transcribing Lecture...")
        model = load_whisper_model()
        transcript_path = transcribe_lecture(media_path, model)

        # convert user uploaded powerpoint to PDF
        st.write("Converting PowerPoint to PDF...")
        slides_path = pptx_to_pdf(pptx_path)

        # generate study guide. Don't crash app if unsuccessful
        try:
            pdf_bytes = generate_study_guide(
                transcript_path=transcript_path,
                slides_path=slides_path,
                learning_objectives=learning_objectives,
                model="gpt-5.5",
                max_output_tokens=20000
            )
            
        except Exception as e:
            st.error(f"Study guide generation failed:\n{e}")
            st.stop

        st.write("Outputting Study Guide...")
        if lecture_file:
            lecture_name = Path(lecture_file.name).stem
            auto_output_name = f"{lecture_name} - Study Guide.pdf"

        st.download_button(
            "Download Study Guide",
            data = pdf_bytes,
            file_name = auto_output_name,
            mime = "application/pdf"
        )
        
        status.update(
            label = "Study Guide Completed!", state = "complete", expanded=True
        )
