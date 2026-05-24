"""
Voice Controller - GUI widget pro hlasové ovládání
"""
from __future__ import annotations

from typing import Optional
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QMessageBox,
    QGroupBox,
    QTextEdit,
    QLineEdit,
    QSlider,
    QSpinBox,
    QFormLayout,
)
from PySide6.QtCore import Qt, QThread, Signal

from .service import VoiceService


class ListenThread(QThread):
    """Thread pro naslouchání hlasovým příkazům"""
    command_received = Signal(str)
    error = Signal(str)
    
    def __init__(self, service: VoiceService, timeout: int = 5):
        super().__init__()
        self.service = service
        self.timeout = timeout
    
    def run(self):
        try:
            command = self.service.listen(timeout=self.timeout)
            if command:
                self.command_received.emit(command.text)
            else:
                self.error.emit("Nepodařilo se rozpoznat příkaz")
        except Exception as e:
            self.error.emit(str(e))


class VoiceWidget(QWidget):
    """Widget pro hlasové ovládání"""
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.service = VoiceService()
        self.listen_thread: Optional[ListenThread] = None
        self._setup_ui()
    
    def _setup_ui(self):
        """Nastaví UI komponenty"""
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Status
        status_group = QGroupBox("Status")
        status_layout = QVBoxLayout()
        
        status = self.service.get_status()
        
        sr_status = "✅ Dostupné" if status["speech_recognition"] else "❌ Nedostupné"
        tts_status = "✅ Dostupné" if status["text_to_speech"] else "❌ Nedostupné"
        
        status_layout.addWidget(QLabel(f"Rozpoznávání řeči: {sr_status}"))
        status_layout.addWidget(QLabel(f"Syntéza řeči (TTS): {tts_status}"))
        
        if not status["speech_recognition_installed"]:
            status_layout.addWidget(QLabel("⚠️ Nainstalujte: pip install SpeechRecognition PyAudio"))
        if not status["tts_installed"]:
            status_layout.addWidget(QLabel("⚠️ Nainstalujte: pip install pyttsx3"))
        
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)
        
        # Hlasové příkazy
        listen_group = QGroupBox("Hlasové příkazy")
        listen_layout = QVBoxLayout()
        
        self.listen_btn = QPushButton("🎤 Poslouchat")
        self.listen_btn.clicked.connect(self._start_listening)
        self.listen_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #667eea, stop:1 #764ba2);
                color: white;
                border: none;
                padding: 15px 30px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 16px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #5a6fd6, stop:1 #6a4190);
            }
            QPushButton:disabled {
                background: #ccc;
            }
        """)
        listen_layout.addWidget(self.listen_btn)
        
        self.listen_result = QLabel("Klikněte na tlačítko a mluvte...")
        self.listen_result.setAlignment(Qt.AlignCenter)
        self.listen_result.setStyleSheet("font-size: 14px; padding: 10px;")
        listen_layout.addWidget(self.listen_result)
        
        listen_group.setLayout(listen_layout)
        layout.addWidget(listen_group)
        
        # Text-to-Speech
        tts_group = QGroupBox("Text na řeč")
        tts_layout = QVBoxLayout()
        
        self.tts_input = QTextEdit()
        self.tts_input.setPlaceholderText("Zadejte text k přečtení...")
        self.tts_input.setMaximumHeight(100)
        tts_layout.addWidget(self.tts_input)
        
        # Nastavení TTS
        settings_layout = QFormLayout()
        
        self.rate_slider = QSlider(Qt.Horizontal)
        self.rate_slider.setRange(100, 300)
        self.rate_slider.setValue(150)
        settings_layout.addRow("Rychlost:", self.rate_slider)
        
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        settings_layout.addRow("Hlasitost:", self.volume_slider)
        
        tts_layout.addLayout(settings_layout)
        
        speak_btn = QPushButton("🔊 Přečíst")
        speak_btn.clicked.connect(self._speak_text)
        tts_layout.addWidget(speak_btn)
        
        tts_group.setLayout(tts_layout)
        layout.addWidget(tts_group)
        
        # Historie
        history_group = QGroupBox("Historie příkazů")
        history_layout = QVBoxLayout()
        
        self.history = QTextEdit()
        self.history.setReadOnly(True)
        self.history.setMaximumHeight(150)
        history_layout.addWidget(self.history)
        
        clear_btn = QPushButton("Vymazat historii")
        clear_btn.clicked.connect(lambda: self.history.clear())
        history_layout.addWidget(clear_btn)
        
        history_group.setLayout(history_layout)
        layout.addWidget(history_group)
        
        layout.addStretch()
    
    def _start_listening(self):
        """Spustí naslouchání"""
        if not self.service.is_speech_recognition_available():
            QMessageBox.warning(
                self,
                "Nedostupné",
                "Rozpoznávání řeči není k dispozici.\n\n"
                "Nainstalujte potřebné knihovny:\n"
                "pip install SpeechRecognition PyAudio"
            )
            return
        
        self.listen_btn.setEnabled(False)
        self.listen_btn.setText("🎤 Naslouchám...")
        self.listen_result.setText("Mluvte nyní...")
        
        self.listen_thread = ListenThread(self.service)
        self.listen_thread.command_received.connect(self._on_command_received)
        self.listen_thread.error.connect(self._on_listen_error)
        self.listen_thread.finished.connect(self._on_listen_finished)
        self.listen_thread.start()
    
    def _on_command_received(self, text: str):
        """Callback při přijetí příkazu"""
        self.listen_result.setText(f'Rozpoznáno: "{text}"')
        self.history.append(f"• {text}")
    
    def _on_listen_error(self, error: str):
        """Callback při chybě"""
        self.listen_result.setText(f"Chyba: {error}")
    
    def _on_listen_finished(self):
        """Callback po dokončení naslouchání"""
        self.listen_btn.setEnabled(True)
        self.listen_btn.setText("🎤 Poslouchat")
    
    def _speak_text(self):
        """Přečte text"""
        text = self.tts_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Chyba", "Zadejte text k přečtení.")
            return
        
        if not self.service.is_tts_available():
            QMessageBox.warning(
                self,
                "Nedostupné",
                "Text-to-speech není k dispozici.\n\n"
                "Nainstalujte: pip install pyttsx3"
            )
            return
        
        # Nastavit parametry
        self.service.set_speech_rate(self.rate_slider.value())
        self.service.set_volume(self.volume_slider.value() / 100.0)
        
        # Přečíst
        if not self.service.speak(text):
            QMessageBox.warning(self, "Chyba", "Nepodařilo se přečíst text.")






