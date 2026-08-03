from dotenv import load_dotenv; load_dotenv()

import os
from pathlib import Path
from openai import OpenAI

import pypandoc
import tempfile
import streamlit as st

# for anki
import json


# create the API instance with project api key
def create_client():
    return OpenAI(
        api_key=os.environ.get("OPENAI_API_KEY")
    )

# upload necessary files
def upload_file(client, file_path):
    with open(file_path, "rb") as f:
        return client.files.create(
            file=f,
            purpose="user_data"
        )
        
def upload_source_files(
    client,
    transcript_path: str | None = None,
    slides_path: str | None = None
):

    transcript = None
    slides = None

    if transcript_path:
        st.write("Uploading Transcript...")
        transcript = upload_file(
            client,
            transcript_path
        )

    if slides_path:
        st.write("Uploading Slides...")
        slides = upload_file(
            client,
            slides_path
        )

    return transcript, slides

# ## define file paths
# files_to_upload = [
#     "Histo Intro I 2025_default.txt", 
#     "Histo Intro I 2025 with Notes.pdf"
# ]

# transcript = client.files.create(
#     file=open(files_to_upload[0], "rb"),
#     purpose="user_data"
# )

# slides = client.files.create(
#     file=open(files_to_upload[1], "rb"),
#     purpose="user_data"
# )
    
# define learning objectives
# learning_objectives = """
# LO 1: Understand the process of tissue preparation and staining.
# LO 2: Understand how different methods of sectioning and preparation may alter the appearance of tissue.
# LO 3: Understand H&E staining and how H&E stains various parts of the cell.
# LO 4: Describe other major types of stains besides H&E and identify which structures they enable us to see.
# LO 5: Understand the basic artifacts that can occur to slide preparation.
# LO 6: Explain the Sequence: Understand and articulate why the key components of histological concepts are presented in the specified sequence.
# LO 7: Master the Components: Explain why mastering the principles and practices of histology is crucial for effective clinical practice and patient care.
# """

# add in system instructions to define role for GPT
def load_system_prompt():
    return Path("prompts/system_prompt.md").read_text(
        encoding="utf-8"
    )

def generate_study_guide(
    learning_objectives: str,
    transcript_path: str | None = None,
    slides_path: str | None = None,
    model: str = "gpt-5.5",
    max_output_tokens: int = 20000
):
    
    client = create_client()
    
    user_prompt = f"""
Answer the following learning objectives:

{learning_objectives}

Return the response as well-formatted Markdown suitable for direct conversion to a PDF.
"""
    
    # Upload transcript
    if transcript_path:
        st.write("Uploading Transcript...")
        with open(transcript_path, "rb") as f:
            transcript = client.files.create(
                file=f,
                purpose="user_data"
            )

    # Upload slides
    if slides_path:
        st.write("Uploading Slides...")
        with open(slides_path, "rb") as f:
            slides = client.files.create(
                file=f,
                purpose="user_data"
            )
    
    # create the prompt
    prompt_input_keys = [
        ["type", "file_id"], 
        ["type", "file_id"], 
        ["type", "text"]
    ]
    
    prompt_input_values = [
        [
            'input_file', 
            transcript.id if transcript_path is not None else None
        ],
        [
            'input_file', 
            slides.id if slides_path is not None else None
        ],
        [
            'input_text', 
            user_prompt
        ]
    ]
    
    prompt_input_content = [
        {key: value for key, value in zip(keys, vals)}
        for keys, vals in zip(prompt_input_keys, prompt_input_values)
            if vals[1] is not None
    ]
    
    prompt_input = [
        {
            "role": "user",
            "content": prompt_input_content
        }
    ]
            
    system_prompt = Path("prompts/system_prompt.md").read_text(
        encoding="utf-8"
    )

    st.write("Writing Study Guide...")
    print(prompt_input)
    response = client.responses.create(
        model=model,
        instructions=system_prompt,
        input=prompt_input,
        
        # FOR DEBUGGING
        # reasoning={
        #     "effort": "minimal"
        # },
        
        max_output_tokens=max_output_tokens
    )

    markdown = response.output_text
    
    pdf_file = tempfile.NamedTemporaryFile(suffix = ".pdf", delete = False)

    st.write("Converting study guide to fancy PDF...")
    pypandoc.convert_text(
        markdown,
        "pdf",
        format="md",
        outputfile=pdf_file.name,
        extra_args=[
            "--pdf-engine=xelatex",
            "--toc",                    # Table of contents
            "--number-sections",        # Number headings
            "-V", "geometry:margin=1in",
            "-V", "fontsize=11pt",
            # "-V", "colorlinks=false",
        ],
    )
    
    with open(pdf_file.name, "rb") as f:
        pdf_bytes = f.read()
    
    return pdf_bytes

def generate_anki_cards(
    learning_objectives: str,
    transcript_path: str | None = None,
    slides_path: str | None = None,
    model: str = "gpt-5.5",
):

    client = create_client()

    anki_prompt = f"""
Generate Anki cards from the following learning objectives:

{learning_objectives}
"""


    transcript, slides = upload_source_files(
        client,
        transcript_path,
        slides_path
    )


    prompt_input_content = []


    if transcript:
        prompt_input_content.append(
            {
                "type": "input_file",
                "file_id": transcript.id
            }
        )


    if slides:
        prompt_input_content.append(
            {
                "type": "input_file",
                "file_id": slides.id
            }
        )


    prompt_input_content.append(
        {
            "type": "input_text",
            "text": anki_prompt
        }
    )


    prompt_input = [
        {
            "role": "user",
            "content": prompt_input_content
        }
    ]


    anki_system_prompt = Path(
        "prompts/anki_system_prompt.md"
    ).read_text(
        encoding="utf-8"
    )


    st.write("Generating Anki Cards...")


    response = client.responses.create(
        model=model,
        instructions=anki_system_prompt,
        input=prompt_input,
        max_output_tokens=20000
    )

    print(response.output_text)
    
    raw_output = response.output_text.strip()

    if raw_output.startswith("```"):
        raw_output = raw_output.replace("```json", "")
        raw_output = raw_output.replace("```", "")
        raw_output = raw_output.strip()

    anki_data = json.loads(raw_output)

    return anki_data
    # print("===== RAW ANKI OUTPUT =====")
    # print(response.output_text)
    # print("============================")

    # return json.loads(
    #     response.output_text
    # )