from pathlib import Path
import tempfile

import fitz


def render_selected_slides(
    pdf_path: str | Path,
    slide_numbers: list[int],
    dpi: int = 160,
) -> dict[int, Path]:
    """
    Render only the requested slide numbers from a PDF.

    Slide numbers are 1-based.
    Returns:
        {
            5: Path(".../slide_005.png"),
            12: Path(".../slide_012.png"),
        }
    """
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"Slide PDF not found: {pdf_path}")

    unique_slide_numbers = sorted(set(slide_numbers))

    if not unique_slide_numbers:
        return {}

    output_dir = Path(
        tempfile.mkdtemp(prefix="mcom_selected_slides_")
    )

    scale = dpi / 72
    matrix = fitz.Matrix(scale, scale)

    rendered: dict[int, Path] = {}

    with fitz.open(pdf_path) as document:
        total_pages = len(document)

        for slide_number in unique_slide_numbers:
            if slide_number < 1 or slide_number > total_pages:
                continue

            page = document[slide_number - 1]
            output_path = output_dir / f"slide_{slide_number:03d}.png"

            pixmap = page.get_pixmap(
                matrix=matrix,
                alpha=False,
            )
            pixmap.save(output_path)

            rendered[slide_number] = output_path

    return rendered