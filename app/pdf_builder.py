# app/pdf_builder.py
import os
from flask import current_app
from xhtml2pdf import pisa
from PyPDF2 import PdfWriter, PdfReader, errors as PyPDF2Errors
from io import BytesIO

class PDFBuilder:
    def __init__(self, task_id):
        self.task_id = task_id
        self.merger = PdfWriter()
        self.temp_miolo_path = os.path.join(current_app.config['GENERATED_REPORTS_FOLDER'], f"temp_miolo_{self.task_id}.pdf")
        self.uploads_folder = os.path.join(current_app.root_path, '..', current_app.config['UPLOAD_FOLDER'])

    def add_cover_page(self, cover_path):
        if cover_path:
            full_path = os.path.join(self.uploads_folder, cover_path)
            if os.path.exists(full_path):
                try:
                    with open(full_path, "rb") as f:
                        self.merger.append(PdfReader(f))
                except PyPDF2Errors.PdfReadError:
                    return "Arquivo de capa corrompido ou inválido."
        return None

    def add_miolo_from_html(self, html_content):
        with open(self.temp_miolo_path, "w+b") as pdf_file:
            pisa_status = pisa.CreatePDF(BytesIO(html_content.encode('UTF-8')), dest=pdf_file)
        if pisa_status.err:
            return f"Falha ao gerar PDF do conteúdo: {pisa_status.err}"
        try:
            with open(self.temp_miolo_path, "rb") as f:
                self.merger.append(PdfReader(f))
        except PyPDF2Errors.PdfReadError:
            return "Ocorreu um erro interno ao gerar o corpo do relatório."
        return None

    def add_final_page(self, final_page_path):
        if final_page_path:
            full_path = os.path.join(self.uploads_folder, final_page_path)
            if os.path.exists(full_path):
                try:
                    with open(full_path, "rb") as f:
                        self.merger.append(PdfReader(f))
                except PyPDF2Errors.PdfReadError:
                    return "Arquivo de página final corrompido ou inválido."
        return None

    def save_and_cleanup(self, final_pdf_path):
        absolute_path = os.path.join(current_app.root_path, '..', final_pdf_path)
        with open(absolute_path, "wb") as f:
            self.merger.write(f)
        try:
            os.remove(self.temp_miolo_path)
        except OSError as e:
            current_app.logger.warning(f"Não foi possível remover arquivo temporário: {e}")
        return absolute_path