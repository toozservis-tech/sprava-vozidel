"""
Email Client Controller - GUI widget pro emailového klienta
"""
from __future__ import annotations

from typing import Optional
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLineEdit,
    QTextEdit,
    QPushButton,
    QLabel,
    QMessageBox,
    QGroupBox,
    QCheckBox,
    QFileDialog,
    QListWidget,
    QListWidgetItem,
)
from PySide6.QtCore import Qt
from pathlib import Path

from .service import EmailService, EmailMessage


class EmailClientWidget(QWidget):
    """Widget pro odesílání emailů"""
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.service = EmailService()
        self.attachments: list[Path] = []
        self._setup_ui()
    
    def _setup_ui(self):
        """Nastaví UI komponenty"""
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Status konfigurace
        self.status_label = QLabel()
        self._update_status()
        layout.addWidget(self.status_label)
        
        # Formulář pro email
        form_group = QGroupBox("Nový email")
        form_layout = QFormLayout()
        
        # Příjemce
        self.to_input = QLineEdit()
        self.to_input.setPlaceholderText("email@example.com")
        form_layout.addRow("Komu:", self.to_input)
        
        # CC
        self.cc_input = QLineEdit()
        self.cc_input.setPlaceholderText("(volitelné)")
        form_layout.addRow("CC:", self.cc_input)
        
        # Předmět
        self.subject_input = QLineEdit()
        self.subject_input.setPlaceholderText("Předmět emailu")
        form_layout.addRow("Předmět:", self.subject_input)
        
        # Tělo emailu
        self.body_input = QTextEdit()
        self.body_input.setPlaceholderText("Text emailu...")
        self.body_input.setMinimumHeight(150)
        form_layout.addRow("Zpráva:", self.body_input)
        
        # HTML checkbox
        self.html_checkbox = QCheckBox("Odeslat jako HTML")
        form_layout.addRow("", self.html_checkbox)
        
        form_group.setLayout(form_layout)
        layout.addWidget(form_group)
        
        # Přílohy
        attachments_group = QGroupBox("Přílohy")
        attachments_layout = QVBoxLayout()
        
        self.attachments_list = QListWidget()
        self.attachments_list.setMaximumHeight(100)
        attachments_layout.addWidget(self.attachments_list)
        
        btn_layout = QHBoxLayout()
        btn_add = QPushButton("Přidat přílohu")
        btn_add.clicked.connect(self._add_attachment)
        btn_remove = QPushButton("Odebrat")
        btn_remove.clicked.connect(self._remove_attachment)
        btn_layout.addWidget(btn_add)
        btn_layout.addWidget(btn_remove)
        btn_layout.addStretch()
        attachments_layout.addLayout(btn_layout)
        
        attachments_group.setLayout(attachments_layout)
        layout.addWidget(attachments_group)
        
        # Tlačítka
        buttons_layout = QHBoxLayout()
        
        btn_send = QPushButton("Odeslat email")
        btn_send.clicked.connect(self._send_email)
        btn_send.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #667eea, stop:1 #764ba2);
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #5a6fd6, stop:1 #6a4190);
            }
        """)
        buttons_layout.addWidget(btn_send)
        
        btn_clear = QPushButton("Vymazat")
        btn_clear.clicked.connect(self._clear_form)
        buttons_layout.addWidget(btn_clear)
        
        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)
        
        layout.addStretch()
    
    def _update_status(self):
        """Aktualizuje status konfigurace"""
        if self.service.is_configured():
            self.status_label.setText("✅ Email je nakonfigurován")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.status_label.setText("⚠️ Email není nakonfigurován. Nastavte SMTP údaje v .env souboru.")
            self.status_label.setStyleSheet("color: orange; font-weight: bold;")
    
    def _add_attachment(self):
        """Přidá přílohu"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Vybrat přílohu", "", "Všechny soubory (*.*)"
        )
        if file_path:
            path = Path(file_path)
            self.attachments.append(path)
            item = QListWidgetItem(path.name)
            item.setData(Qt.UserRole, str(path))
            self.attachments_list.addItem(item)
    
    def _remove_attachment(self):
        """Odebere vybranou přílohu"""
        current = self.attachments_list.currentItem()
        if current:
            path = Path(current.data(Qt.UserRole))
            if path in self.attachments:
                self.attachments.remove(path)
            self.attachments_list.takeItem(self.attachments_list.row(current))
    
    def _clear_form(self):
        """Vymaže formulář"""
        self.to_input.clear()
        self.cc_input.clear()
        self.subject_input.clear()
        self.body_input.clear()
        self.html_checkbox.setChecked(False)
        self.attachments.clear()
        self.attachments_list.clear()
    
    def _send_email(self):
        """Odešle email"""
        # Validace
        to = self.to_input.text().strip()
        if not to:
            QMessageBox.warning(self, "Chyba", "Zadejte příjemce emailu.")
            return
        
        subject = self.subject_input.text().strip()
        if not subject:
            QMessageBox.warning(self, "Chyba", "Zadejte předmět emailu.")
            return
        
        body = self.body_input.toPlainText().strip()
        if not body:
            QMessageBox.warning(self, "Chyba", "Zadejte text emailu.")
            return
        
        if not self.service.is_configured():
            QMessageBox.warning(
                self, 
                "Email není nakonfigurován",
                "Pro odesílání emailů je nutné nastavit SMTP údaje v konfiguračním souboru."
            )
            return
        
        # Příprava zprávy
        to_list = [e.strip() for e in to.split(",") if e.strip()]
        cc_list = None
        if self.cc_input.text().strip():
            cc_list = [e.strip() for e in self.cc_input.text().split(",") if e.strip()]
        
        html_body = None
        if self.html_checkbox.isChecked():
            html_body = f"<html><body>{body.replace(chr(10), '<br>')}</body></html>"
        
        message = EmailMessage(
            to=to_list,
            subject=subject,
            body=body,
            html_body=html_body,
            cc=cc_list,
            attachments=self.attachments if self.attachments else None
        )
        
        try:
            self.service.send_email(message)
            QMessageBox.information(self, "Úspěch", "Email byl úspěšně odeslán!")
            self._clear_form()
        except Exception as e:
            QMessageBox.critical(
                self, 
                "Chyba", 
                f"Nepodařilo se odeslat email:\n{str(e)}"
            )






