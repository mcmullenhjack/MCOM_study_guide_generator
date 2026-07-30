import subprocess
from pathlib import Path
import shutil
import platform
import tempfile

def find_soffice():
    # First, check if it's on the system PATH
    soffice = shutil.which("soffice")
    if soffice:
        return soffice

    system = platform.system()

    if system == "Darwin":  # macOS
        candidates = [
            "/Applications/LibreOffice.app/Contents/MacOS/soffice",
            str(Path.home() / "Applications/LibreOffice.app/Contents/MacOS/soffice"),
        ]
    elif system == "Windows":
        candidates = [
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        ]
    else:  # Linux
        candidates = [
            "/usr/bin/soffice",
            "/snap/bin/libreoffice",
        ]

    for path in candidates:
        if Path(path).exists():
            return path

    raise FileNotFoundError("LibreOffice (soffice) not found.")


def pptx_to_pdf(pptx_path):
    
    soffice = find_soffice()
    
    # pptx_path = Path(pptx_path).resolve()
    
    with tempfile.TemporaryDirectory() as temp_dir:

        subprocess.run(
            [
                soffice,
                "--headless",
                "--convert-to", 
                "pdf",
                "--outdir", 
                temp_dir,
                pptx_path,
            ],
            check=True,
        )
        
        pdf_name = Path(pptx_path).with_suffix(".pdf").name
        generated_pdf = Path(temp_dir) / pdf_name
        
        # create a persistent temp file
        temp_pdf = tempfile.NamedTemporaryFile(
            suffix = ".pdf",
            delete = False
        )
        
        temp_pdf.close()
        
        shutil.copy2(generated_pdf, temp_pdf.name)
        

    return temp_pdf.name