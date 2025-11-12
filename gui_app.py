import os
import sys
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr

from PySide6.QtCore import QThread, Signal, QTimer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QLineEdit,
    QFileDialog, QComboBox, QVBoxLayout, QHBoxLayout, QTextEdit, QMessageBox, QFrame
)

import file_translator as ft


class _LogStream:
    def __init__(self, emit_fn):
        self.emit_fn = emit_fn
        self._buf = ""

    def write(self, s):
        if not s:
            return 0
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line:
                self.emit_fn(line)
        return len(s)
 
    def flush(self):
        if self._buf:
            self.emit_fn(self._buf)
            self._buf = ""


# ---------- Worker that runs the translator in a background thread ----------
class TranslateWorker(QThread):
    log = Signal(str)
    done = Signal(int)   # return code

    def __init__(self, pdf_path: str, lang_code: str, parent=None):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.lang_code = lang_code

    def _map_language(self, code: str) -> str:
        mapping = {
            "zh-TW": "Traditional Chinese",
            "zh-CN": "Simplified Chinese",
            "ja": "Japanese",
            "ko": "Korean",
            "es": "Spanish",
            "fr": "French",
            "de": "German",
            "en": "English",
        }
        return mapping.get(code, code)

    def run(self):
        repo_root = Path(__file__).resolve().parent
        lang_name = self._map_language(self.lang_code)
        self.log.emit(f"[worker] cwd -> {repo_root}")

        # Ensure relative paths inside file_translator.py resolve like README
        old_cwd = os.getcwd()
        try:
            os.chdir(repo_root)
            # Ensure output directories exist for this document
            stem = Path(self.pdf_path).stem
            os.makedirs(Path("img") / stem, exist_ok=True)
            os.makedirs(Path("text") / stem, exist_ok=True)
            os.makedirs(Path("latex") / stem, exist_ok=True)
            os.makedirs(Path("translated_pdf") / stem, exist_ok=True)
            log_stream = _LogStream(self.log.emit)
            self.log.emit(f"[info] Starting translator core with language: {lang_name}")
            rc = 0
            try:
                with redirect_stdout(log_stream), redirect_stderr(log_stream):
                    ft.file_translator(self.pdf_path, lang_name)
            except Exception as e:
                self.log.emit(f"[error] {e}")
                rc = 1

            # Verify expected output exists
            try:
                stem = Path(self.pdf_path).stem
                out_pdf = Path("translated_pdf") / stem / f"{stem}_{lang_name}.pdf"
                if not out_pdf.exists():
                    self.log.emit(f"[error] Expected output not found: {out_pdf}")
                    rc = 1
                else:
                    self.log.emit(f"[success] Output ready: {out_pdf}")
            except Exception as e:
                self.log.emit(f"[warn] Could not verify output: {e}")
            self.done.emit(rc)
        finally:
            os.chdir(old_cwd)
            

# ---------- Main Window ----------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("File Translator — GUI")
        self.setMinimumSize(720, 520)

        # File picker row
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("Choose a PDF to translate…")
        self.file_edit.setReadOnly(True)

        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self.on_browse)

        file_row = QHBoxLayout()
        file_row.addWidget(QLabel("Source PDF:"))
        file_row.addWidget(self.file_edit, 1)
        file_row.addWidget(browse_btn)

        # Language row
        self.lang_combo = QComboBox()
        # Display name → code mapping (you can add more)
        self.lang_map = {
            "Traditional Chinese (zh-TW)": "zh-TW",
            "Simplified Chinese (zh-CN)": "zh-CN",
            "Japanese (ja)": "ja",
            "Korean (ko)": "ko",
            "Spanish (es)": "es",
            "French (fr)": "fr",
            "German (de)": "de",
            "English (en)": "en",
        }
        self.lang_combo.addItems(self.lang_map.keys())
        self.lang_combo.setCurrentText("Traditional Chinese (zh-TW)")

        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("Target language:"))
        lang_row.addWidget(self.lang_combo, 1)

        # Run button
        self.run_btn = QPushButton("Start Translation")
        self.run_btn.setEnabled(False)
        self.run_btn.clicked.connect(self.on_run_clicked)

        # Status label
        self.status_label = QLabel("Idle")
        self.status_label.setStyleSheet("color: #666;")

        run_row = QHBoxLayout()
        run_row.addWidget(self.run_btn)
        run_row.addStretch(1)
        run_row.addWidget(self.status_label)

        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setFrameShadow(QFrame.Sunken)

        # Log area
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("Logs will appear here…")

        # Layout
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addLayout(file_row)
        layout.addLayout(lang_row)
        layout.addLayout(run_row)
        layout.addWidget(divider)
        layout.addWidget(self.log_view, 1)

        self.setCentralWidget(root)

        # Worker handle
        self.worker = None

        # Gentle check for GEMINI_API_KEY so users get a nice prompt
        if "GEMINI_API_KEY" not in os.environ:
            self.append_log("[hint] GEMINI_API_KEY not found in environment. If your translator needs it, set it before running.")

    # ---------- UI helpers ----------
    def append_log(self, text: str):
        self.log_view.append(text)

    def on_browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a PDF", str(Path.home()), "PDF files (*.pdf)")
        if not path:
            return
        self.file_edit.setText(path)
        self.run_btn.setEnabled(True)

    def on_run_clicked(self):
        pdf_path = self.file_edit.text().strip()
        if not pdf_path:
            QMessageBox.warning(self, "No file", "Please choose a PDF first.")
            return

        if not Path(pdf_path).exists() or Path(pdf_path).suffix.lower() != ".pdf":
            QMessageBox.critical(self, "Invalid file", "Please select a valid .pdf file.")
            return

        lang_display = self.lang_combo.currentText()
        lang_code = self.lang_map.get(lang_display, "zh-TW")

        # Lock UI
        self.run_btn.setEnabled(False)
        self.status_label.setText(f"Running… ({lang_code})")
        self.append_log(f"[info] Starting translation\n- file: {pdf_path}\n- lang: {lang_code}\n")

        # Start background worker
        self.worker = TranslateWorker(pdf_path=pdf_path, lang_code=lang_code)
        self.worker.log.connect(self.append_log)
        self.worker.done.connect(self.on_worker_done)
        self.worker.start()

    def on_worker_done(self, return_code: int):
        if return_code == 0:
            self.status_label.setText("Done")
            self.append_log("\n[success] Translation completed.")
        else:
            self.status_label.setText("Failed")
            self.append_log(f"\n[error] Translator exited with code {return_code}.")
            QMessageBox.critical(
                self,
                "Translation failed",
                "The translator encountered an error.\nCheck the log panel for details."
            )
        # Re-enable run button to allow another try
        self.run_btn.setEnabled(True)
        
        # Exit the application cleanly from the GUI thread with the worker's return code
        # QTimer.singleShot(0, lambda: QApplication.instance().exit(return_code))


def run_gui():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
