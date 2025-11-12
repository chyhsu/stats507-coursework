from model import gemini_prompt
from util import convert_pdf_to_images, convert_pdf_to_text_with_model,convert_pdf_to_text, get_latex_from_response_text, convert_latex_to_pdf
from pathlib import Path
import os


def file_translator(file_path, language):
    path = Path(file_path)
    stem = path.stem
    
    # Compute output paths (directories are created by the GUI worker)
    img_path = Path("img") / stem
    text_path = Path("text") / stem
    latex_path = Path("latex") / stem
    output_pdf_path = Path("translated_pdf") / stem
    
    latex_file_path = latex_path / f"{stem}.tex"
    output_pdf_file_path = output_pdf_path / f"{stem}_{language}.pdf"

    # Process PDF
    convert_pdf_to_images(file_path, img_path)
    prompt = convert_pdf_to_text_with_model(file_path, text_path)

    # Generate LaTeX from Gemini
    gemini_result = gemini_prompt(str(prompt), img_path, language)
    latex = get_latex_from_response_text(gemini_result)
    
    # Save LaTeX file
    print("Saving LaTeX file...")
    with open(latex_file_path, "w", encoding="utf-8") as f:
        f.write(latex)
    
    # Convert LaTeX to PDF
    print("Converting LaTeX to PDF...")
    convert_latex_to_pdf(latex_file_path, output_pdf_file_path)


