from dotenv import load_dotenv; load_dotenv()

import os
from pathlib import Path
from openai import OpenAI
import re

import pypandoc
import tempfile
import streamlit as st

from typing import Literal
from pydantic import BaseModel, Field
import subprocess

# for anki
import json

from slide_renderer import render_selected_slides


### creating pydantic classes for use in structured outputs
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
    
# Class to store outputs returned by the python functions
class GeneratedStudyGuide(BaseModel):
    markdown: str
    illustrated_markdown: str
    pdf_bytes: bytes
    visuals: list[SelectedVisual]
    
# Create StructuredOutput that explains how Anki cards shouls be formatted
class AnkiCard(BaseModel):
    text: str = Field(
        description=(
            "A complete standalone sentence containing valid Anki "
            "cloze syntax such as {{c1::answer}}."
        )
    )

    extra: str = Field(
        default="",
        description=(
            "Optional concise supporting context shown after answering. "
            "Do not repeat the clozed answer."
        )
    )

    tags: list[str] = Field(
        default_factory=list,
        description="Specific tags relevant to the card."
    )

    source: str = Field(
        default="",
        description=(
            "The relevant learning objective or study-guide section."
        )
    )


class AnkiDeckResponse(BaseModel):
    deck_name: str = Field(
        description="A concise name describing the lecture or topic."
    )

    cards: list[AnkiCard] = Field(
        description="The selected AnKing-style Cloze notes."
    )
    

class RetrievalObjective(BaseModel):
    title: str = Field(
        description=(
            "A concise name for one high-value retrieval objective."
        )
    )

    description: str = Field(
        description=(
            "A concise explanation of what the learner should be able "
            "to retrieve and why the information belongs together."
        )
    )

    source_section: str = Field(
        description=(
            "The relevant learning objective or study-guide section."
        )
    )


class LearningObjectivePlan(BaseModel):
    learning_objective: str = Field(
        description=(
            "The learning objective exactly as represented in the study guide."
        )
    )

    major_concepts: list[str] = Field(
        description=(
            "The major concepts required to master this learning objective."
        )
    )

    retrieval_objectives: list[RetrievalObjective] = Field(
        description=(
            "The minimum set of meaningful retrieval objectives needed "
            "to master this learning objective."
        )
    )


class AnkiMasteryPlan(BaseModel):
    deck_name: str = Field(
        description="A concise deck name based on the study guide."
    )

    learning_objectives: list[LearningObjectivePlan] = Field(
        description=(
            "The complete mastery plan organized by learning objective."
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

# fix markdown table output/styling
def add_longtable_row_separators(latex: str) -> str:
    """
    Add horizontal separators between body rows of Pandoc-generated
    longtable environments.

    Pandoc places table body rows after \\endlastfoot and before
    \\end{longtable}. This function adds \\midrule between those rows
    while preserving the existing header and bottom rules.
    """
    latex = latex.replace(
        r"\begin{document}",
        "\n".join(
            [
                r"\renewcommand{\arraystretch}{1.15}",
                r"\setlength{\tabcolsep}{7pt}",
                r"\begin{document}",
            ]
        ),
        1,
    )

    lines = latex.splitlines()
    output: list[str] = []

    inside_longtable = False
    inside_table_body = False
    body_lines: list[str] = []

    for line in lines:
        if r"\begin{longtable}" in line:
            inside_longtable = True

        if inside_longtable and r"\endlastfoot" in line:
            output.append(line)
            inside_table_body = True
            body_lines = []
            continue

        if inside_table_body and r"\end{longtable}" in line:
            row_end_indexes = [
                index
                for index, body_line in enumerate(body_lines)
                if body_line.rstrip().endswith(r"\\")
            ]

            # Do not add a separator after the final body row because
            # longtable already supplies its bottom rule.
            indexes_to_separate = set(row_end_indexes[:-1])

            for index, body_line in enumerate(body_lines):
                output.append(body_line)

                if index in indexes_to_separate:
                    output.append(r"\midrule\noalign{}")

            output.append(line)

            inside_table_body = False
            inside_longtable = False
            body_lines = []
            continue

        if inside_table_body:
            body_lines.append(line)
        else:
            output.append(line)

    # Defensive fallback for malformed or incomplete LaTeX.
    if body_lines:
        output.extend(body_lines)

    return "\n".join(output)

def strip_latex_for_length(text: str) -> str:
    """
    Produce a rough plain-text version of a LaTeX table cell so that
    compact-table decisions can be based on visible content length.
    """
    text = re.sub(
        r"\\(?:textbf|textit|emph|mathrm|mathbf|mathit)\{([^{}]*)\}",
        r"\1",
        text,
    )

    text = re.sub(
        r"\\begin\{[^{}]+\}|\\end\{[^{}]+\}",
        "",
        text,
    )

    text = re.sub(
        r"\\[A-Za-z]+(?:\[[^\]]*\])?",
        "",
        text,
    )

    text = re.sub(
        r"[{}$]",
        "",
        text,
    )

    return " ".join(text.split())

def compact_simple_longtables(latex: str) -> str:
    """
    Convert short, simple two-column Pandoc longtables to natural-width
    tables while leaving explanatory tables full width.
    """

    longtable_pattern = re.compile(
        r"\\begin\{longtable\}\[\]\{(?P<columns>.*?)\}"
        r"(?P<body>.*?)"
        r"\\end\{longtable\}",
        flags=re.DOTALL,
    )

    def transform(match: re.Match) -> str:
        columns = match.group("columns")
        body = match.group("body")

        # Count Pandoc paragraph columns in the existing specification.
        paragraph_column_count = len(
            re.findall(r"p\{", columns)
        )

        if paragraph_column_count != 2:
            return match.group(0)

        # Only inspect actual body rows, not repeated headers or footers.
        if r"\endlastfoot" not in body:
            return match.group(0)

        table_body = body.split(
            r"\endlastfoot",
            maxsplit=1,
        )[1]

        row_texts: list[str] = []

        for row in table_body.split(r"\\"):
            if "&" not in row:
                continue

            cells = row.split("&")

            if len(cells) != 2:
                return match.group(0)

            visible_cells = [
                strip_latex_for_length(cell)
                for cell in cells
            ]

            row_texts.extend(visible_cells)

        if not row_texts:
            return match.group(0)

        longest_cell = max(
            len(cell)
            for cell in row_texts
        )

        body_row_count = len(row_texts) // 2

        # Conservative compact-table rules:
        # - no more than 5 body rows
        # - no visible cell longer than 35 characters
        if body_row_count > 5 or longest_cell > 35:
            return match.group(0)

        compact_columns = r"@{}lr@{}"

        return (
            rf"\begin{{longtable}}[]{{{compact_columns}}}"
            f"{body}"
            r"\end{longtable}"
        )

    return longtable_pattern.sub(
        transform,
        latex,
    )
    

###
def style_latex_figures(latex: str) -> str:
    """
    Constrain slide images and prevent them from being clipped at
    page boundaries.
    """

    # Normalize existing figure placement arguments.
    latex = re.sub(
        r"\\begin\{figure\}(?:\[[^\]]*\])?",
        r"\\begin{figure}[htbp]",
        latex,
    )

    # Apply maximum dimensions to images that do not already specify them.
    latex = latex.replace(
        r"\begin{document}",
        "\n".join(
            [
                r"\setkeys{Gin}{%",
                r"  width=\linewidth,",
                r"  height=0.72\textheight,",
                r"  keepaspectratio",
                r"}",
                r"\begin{document}",
            ]
        ),
        1,
    )

    return latex

def generate_study_guide(
    learning_objectives: str,
    transcript_path: str | None = None,
    slides_path: str | None = None,
    model: str = "gpt-5.5",
    max_output_tokens: int = 20000,
) -> GeneratedStudyGuide:
    if not transcript_path and not slides_path:
        raise ValueError(
            "At least one source file must be provided."
        )

    client = create_client()

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
    
    Path("debug_study_guide.md").write_text(
        study_guide_markdown,
        encoding="utf-8",
    )
    
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

    # with tempfile.NamedTemporaryFile(
    #     suffix=".pdf",
    #     delete=False,
    # ) as pdf_file:
    #     pdf_path = Path(pdf_file.name)

    try:
        st.write("Converting study guide to fancy PDF...")

        # pypandoc.convert_text(
        #     illustrated_markdown,
        #     "latex",
        #     format="md",
        #     outputfile="debug.tex",
        #     extra_args=[
        #         "--standalone",
        #         "--toc",
        #         "--number-sections",
        #         "-V", "geometry:margin=1in",
        #         "-V", "fontsize=11pt",
        #         "-V", "mainfont=Libertinus Serif",
        #     ],
        # )
        
        # pypandoc.convert_text(
        #     illustrated_markdown,
        #     "pdf",
        #     format="md",
        #     outputfile=str(pdf_path),
        #     extra_args=[
        #         "--pdf-engine=xelatex",
        #         "--toc",
        #         "--number-sections",
        #         "-V", "geometry:margin=1in",
        #         "-V", "fontsize=11pt",
        #         "-V", "mainfont=Libertinus Serif",
        #         "-V", "mathfont=Libertinus Math",
        #         "-V", "monofont=DejaVu Sans Mono",
        #     ],
        # )
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)

            tex_path = temp_dir_path / "study_guide.tex"
            compiled_pdf_path = temp_dir_path / "study_guide.pdf"

            # Step 1: Convert Markdown to complete standalone LaTeX.
            pypandoc.convert_text(
                illustrated_markdown,
                "latex",
                format="md",
                outputfile=str(tex_path),
                extra_args=[
                    "--standalone",
                    "--toc",
                    "--number-sections",
                    "-V", "geometry:margin=1in",
                    "-V", "fontsize=11pt",
                    "-V", "mainfont=Libertinus Serif",
                    "-V", "mathfont=Libertinus Math",
                    "-V", "monofont=DejaVu Sans Mono",
                ],
            )

            # Step 2: Add separators between table body rows.
            latex = tex_path.read_text(encoding="utf-8")
            
            styled_latex = add_longtable_row_separators(
                latex
            )
            styled_latex = compact_simple_longtables(
                styled_latex
            )

            styled_latex = style_latex_figures(
                styled_latex
            )
            
            tex_path.write_text(
                styled_latex,
                encoding="utf-8",
            )

            # Optional temporary debugging copy.
            Path("debug_styled.tex").write_text(
                styled_latex,
                encoding="utf-8",
            )

            # Step 3: Compile twice so the TOC and references resolve.
            xelatex_command = [
                "xelatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                tex_path.name,
            ]

            for _ in range(2):
                completed_process = subprocess.run(
                    xelatex_command,
                    cwd=temp_dir_path,
                    capture_output=True,
                    text=True,
                )

                if completed_process.returncode != 0:
                    raise RuntimeError(
                        "XeLaTeX compilation failed.\n\n"
                        f"STDOUT:\n{completed_process.stdout}\n\n"
                        f"STDERR:\n{completed_process.stderr}"
                    )

            if not compiled_pdf_path.exists():
                raise RuntimeError(
                    "XeLaTeX completed without creating the expected PDF."
                )

            pdf_bytes = compiled_pdf_path.read_bytes()

        # pdf_bytes = pdf_path.read_bytes()

    except Exception as e:
        raise RuntimeError(
            f"Failed to convert study guide to PDF.\n\n{e}"
        ) from e
        
    return GeneratedStudyGuide(
        markdown=study_guide_markdown,
        illustrated_markdown=illustrated_markdown,
        pdf_bytes=pdf_bytes,
        visuals=selected_visuals,
    )

    # finally:
    #     pdf_path.unlink(missing_ok=True)

# define function to call GPT to create an anki card outline
def generate_anki_mastery_plan(
    study_guide_markdown: str,
    model: str = "gpt-5.5",
) -> AnkiMasteryPlan:
    client = create_client()

    planning_system_prompt = Path(
        "prompts/anki_planning_prompt.md"
    ).read_text(
        encoding="utf-8"
    )

    prompt_input = [
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "Create a mastery plan for an AnKing-style deck "
                        "from the following study guide."
                    ),
                },
                {
                    "type": "input_text",
                    "text": study_guide_markdown,
                },
            ],
        }
    ]

    response = client.responses.parse(
        model=model,
        instructions=planning_system_prompt,
        input=prompt_input,
        text_format=AnkiMasteryPlan,
        max_output_tokens=12000,
    )

    mastery_plan = response.output_parsed

    if mastery_plan is None:
        raise RuntimeError(
            "The model did not return a valid Anki mastery plan."
        )

    return mastery_plan

# define function that uses GPT to generate anki cards
def generate_anki_cards(
    mastery_plan: AnkiMasteryPlan,
    model: str = "gpt-5.5",
) -> AnkiDeckResponse:

    client = create_client()

    anki_user_prompt = """
Create the minimum number of high-quality AnKing-style Cloze notes
needed to satisfy the provided mastery plan.

Treat each retrieval objective as an educational target, not as a
requirement to create exactly one note.

Several tightly related retrieval objectives may be represented by one
strong note when that improves retrieval efficiency.

A retrieval objective may require more than one note only when its
parts must be recalled independently.
"""

    # prompt_input_content = []

    prompt_input_content = [
        {
            "type": "input_text",
            "text": anki_user_prompt,
        },
        {
            "type": "input_text",
            "text": mastery_plan.model_dump_json(indent=2),
        },
    ]


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

    response = client.responses.parse(
        model=model,
        instructions=anki_system_prompt,
        input=prompt_input,
        text_format=AnkiDeckResponse,
        max_output_tokens=20000,
    )

    anki_deck = response.output_parsed

    if anki_deck is None:
        raise RuntimeError(
            "The model did not return a valid structured Anki deck."
        )
    debug_json_path = Path("debug_anki_deck.json")

    # debug_json_path.write_text(
    #     anki_deck.model_dump_json(indent=2),
    #     encoding="utf-8",
    # )

    # print(f"Saved Anki JSON to: {debug_json_path.resolve()}")
    
    print(f"Anki notes returned: {len(anki_deck.cards)}")
    
    return anki_deck