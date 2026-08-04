from dotenv import load_dotenv; load_dotenv()

import os
from pathlib import Path
from openai import OpenAI

import pypandoc
import tempfile
import streamlit as st

from pydantic import BaseModel, Field

# for anki
import json

from slide_renderer import render_selected_slides

### creating ydantic classes for use in structured outputs
class SelectedVisual(BaseModel):
    slide_number: int = Field(
        description="The original PowerPoint slide number, starting at 1."
    )
    insert_after: str = Field(
        description=(
            "The exact Markdown heading from study_guide_markdown "
            "after which this visual should be inserted."
        )
    )
    caption: str = Field(
        description=(
            "A concise, title-style caption naming the concept shown. "
            "Prefer 3–10 words. Do not begin with 'Figure' and do not end with a period."
        )
    )
    reason: str = Field(
        description=(
            "A brief explanation of why the visual materially improves "
            "understanding of the associated concept."
        )
    )
    figure_insight: str = Field(
        description=(
            "One or two concise sentences explaining what the student "
            "should learn from the figure. Focus on the educational takeaway, "
            "not merely a description of what appears in the image."
        )
    )


class StudyGuideResponse(BaseModel):
    study_guide_markdown: str = Field(
        description=(
            "The complete high-yield study guide in publication-ready "
            "GitHub-flavored Markdown."
        )
    )
    visuals: list[SelectedVisual] = Field(
        default_factory=list,
        description=(
            "A small set of high-value slide visuals to insert into the guide. "
            "Return an empty list when no slide visual materially improves understanding."
        )
    )
    
    
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


def insert_slide_visuals(
    markdown: str,
    visuals: list[SelectedVisual],
    slide_images: dict[int, Path],
) -> str:
    """
    Insert selected slide images after exact Markdown headings.
    """
    for visual in visuals:
        image_path = slide_images.get(visual.slide_number)

        if image_path is None:
            continue

        heading = visual.insert_after.strip()
        caption = visual.caption.strip()

        if heading not in markdown:
            continue

        figure_markdown = (
            "\n\n"
            f"![{caption}]({image_path.resolve().as_posix()})\n\n"
            f"> **Study Tip**\n"
            f">\n"
            f"> {visual.figure_insight.strip()}\n"
        )

        markdown = markdown.replace(
            heading,
            heading + figure_markdown,
            1,
        )

    return markdown

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
    max_output_tokens: int = 20000,
):
    if not transcript_path and not slides_path:
        raise ValueError(
            "At least one source file must be provided."
        )

    client = create_client()

#     user_prompt = f"""
# Answer the following learning objectives:

# {learning_objectives}

# Return the study guide as well-formatted Markdown suitable for direct conversion to a PDF.

# When slide images are provided, select only a small number of visuals that materially improve understanding of the study guide.

# Prefer labeled diagrams, molecular structures, pathways, anatomical or histological images, mechanisms, and comparison figures.

# Do not select title slides, learning-objective slides, citation slides, decorative images, redundant visuals, or primarily text-based slides.

# For each selected visual, identify the exact Markdown heading after which it should appear.

# For every selected visual, explain in one or two concise sentences what the student should learn from the figure rather than merely describing what is shown.

# If no visual is educationally useful, select none.
# """

    user_prompt = f"""
Answer the following learning objectives:

{learning_objectives}

Return the study guide as well-formatted Markdown suitable for direct conversion to a PDF.

When a slide deck is provided, select only a small number of visuals that materially improve understanding of the study guide.

The study guide must remain complete and understandable even if every selected visual were removed.

Visuals should reinforce understanding, not replace essential explanations, comparisons, mechanisms, definitions, or tables.

Select visuals only when they communicate information more effectively than concise text alone.

Prefer visuals that clarify:
- spatial relationships
- structural organization
- sequential processes
- comparisons between related concepts
- complex mechanisms
- visual patterns or features that are difficult to understand through text alone

Do not select visuals that are primarily decorative, redundant with the accompanying text, or unlikely to improve understanding.

Do not select title slides, learning-objective slides, citation slides, or other administrative slides.

For each selected visual:
- identify the original slide number
- identify the exact Markdown heading after which it should be inserted

For every selected visual, explain in one or two concise sentences what the student should learn from the figure rather than merely describing what it shows.

If no visual meaningfully improves understanding, select none.
"""

    transcript, slides = upload_source_files(
        client=client,
        transcript_path=transcript_path,
        slides_path=slides_path,
    )

    prompt_input_content: list[dict] = []

    if transcript:
        prompt_input_content.append(
            {
                "type": "input_file",
                "file_id": transcript.id,
            }
        )

    if slides:
        prompt_input_content.append(
            {
                "type": "input_file",
                "file_id": slides.id,
            }
        )

    prompt_input_content.append(
        {
            "type": "input_text",
            "text": user_prompt,
        }
    )

    prompt_input = [
        {
            "role": "user",
            "content": prompt_input_content,
        }
    ]

    system_prompt = load_system_prompt()

    st.write("Writing Study Guide...")

    response = client.responses.parse(
        model=model,
        instructions=system_prompt,
        input=prompt_input,
        text_format=StudyGuideResponse,
        max_output_tokens=max_output_tokens,
    )

    result = response.output_parsed

    if result is None:
        raise RuntimeError(
            "The model did not return a valid structured study-guide response."
        )

    study_guide_markdown = result.study_guide_markdown
    selected_visuals = result.visuals

    illustrated_markdown = study_guide_markdown

    if slides_path and selected_visuals:
        st.write("Rendering selected slide visuals...")

        selected_slide_numbers = [
            visual.slide_number
            for visual in selected_visuals
        ]

        rendered_slides = render_selected_slides(
            pdf_path=slides_path,
            slide_numbers=selected_slide_numbers,
        )

        illustrated_markdown = insert_slide_visuals(
            markdown=study_guide_markdown,
            visuals=selected_visuals,
            slide_images=rendered_slides,
    )

    print("===== SELECTED VISUALS =====")
    for visual in result.visuals:
        print(visual.model_dump())
    print("============================")

    with tempfile.NamedTemporaryFile(
        suffix=".pdf",
        delete=False,
    ) as pdf_file:
        pdf_path = Path(pdf_file.name)

    try:
        st.write("Converting study guide to fancy PDF...")

        pypandoc.convert_text(
            illustrated_markdown,
            "latex",
            format="md",
            outputfile="debug.tex",
            extra_args=[
                "--standalone",
                "--toc",
                "--number-sections",
                "-V", "geometry:margin=1in",
                "-V", "fontsize=11pt",
                "-V", "mainfont=Libertinus Serif",
            ],
        )
        
        pypandoc.convert_text(
            illustrated_markdown,
            "pdf",
            format="md",
            outputfile=str(pdf_path),
            extra_args=[
                "--pdf-engine=xelatex",
                "--toc",
                "--number-sections",
                "-V", "geometry:margin=1in",
                "-V", "fontsize=11pt",
                "-V", "mainfont=Libertinus Serif",
                "-V", "monofont=Libertinus Mono",
            ],
        )

        return pdf_path.read_bytes()

    finally:
        pdf_path.unlink(missing_ok=True)


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