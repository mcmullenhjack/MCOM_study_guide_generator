import whisper
from whisper.utils import get_writer
import tempfile

# model = whisper.load_model("base")

def transcribe_lecture(media_path, model, output_dir=None):

    result = model.transcribe(str(media_path))

    temp = tempfile.NamedTemporaryFile(
        mode = "w",
        suffix = ".txt",
        delete = False,
        encoding = "utf-8"
    )
    
    temp.write(result["text"])
    temp.close()
    
    return temp.name
        
    # txt_writer = get_writer("txt", output_directory)
    # txt_writer(result, lecture_file)


