"""
PDF Manager Controller - GUI widget pro správu PDF
"""
from __future__ import annotations

from typing import Optional, List
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QMessageBox,
    QGroupBox,
    QFileDialog,
    QListWidget,
    QListWidgetItem,
    QSpinBox,
    QLineEdit,
    QTextEdit,
    QTabWidget,
    QFormLayout,
    QComboBox,
)
from PySide6.QtCore import Qt

from .service import PDFService


class PDFManagerWidget(QWidget):
    """Widget pro správu PDF souborů"""
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.service = PDFService()
        self.selected_files: List[Path] = []
        self._setup_ui()
    
    def _setup_ui(self):
        """Nastaví UI komponenty"""
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Status
        self.status_label = QLabel()
        self._update_status()
        layout.addWidget(self.status_label)
        
        # Tab widget pro různé operace
        tabs = QTabWidget()
        
        # Tab: Sloučení PDF
        merge_tab = self._create_merge_tab()
        tabs.addTab(merge_tab, "Sloučit PDF")
        
        # Tab: Rozdělení PDF
        split_tab = self._create_split_tab()
        tabs.addTab(split_tab, "Rozdělit PDF")
        
        # Tab: Rotace
        rotate_tab = self._create_rotate_tab()
        tabs.addTab(rotate_tab, "Rotace")
        
        # Tab: Vytvořit PDF
        create_tab = self._create_create_tab()
        tabs.addTab(create_tab, "Vytvořit PDF")
        
        layout.addWidget(tabs)
    
    def _update_status(self):
        """Aktualizuje status"""
        if self.service.is_available():
            self.status_label.setText("✅ PDF nástroje jsou k dispozici")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.status_label.setText("⚠️ PyPDF2 není nainstalován. Spusťte: pip install PyPDF2")
            self.status_label.setStyleSheet("color: orange; font-weight: bold;")
    
    def _create_merge_tab(self) -> QWidget:
        """Vytvoří tab pro sloučení PDF"""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)
        
        # Seznam souborů
        group = QGroupBox("Soubory ke sloučení")
        group_layout = QVBoxLayout()
        
        self.merge_list = QListWidget()
        group_layout.addWidget(self.merge_list)
        
        btn_layout = QHBoxLayout()
        btn_add = QPushButton("Přidat PDF")
        btn_add.clicked.connect(self._add_pdf_to_merge)
        btn_remove = QPushButton("Odebrat")
        btn_remove.clicked.connect(self._remove_pdf_from_merge)
        btn_up = QPushButton("↑")
        btn_up.clicked.connect(self._move_up)
        btn_down = QPushButton("↓")
        btn_down.clicked.connect(self._move_down)
        
        btn_layout.addWidget(btn_add)
        btn_layout.addWidget(btn_remove)
        btn_layout.addWidget(btn_up)
        btn_layout.addWidget(btn_down)
        btn_layout.addStretch()
        
        group_layout.addLayout(btn_layout)
        group.setLayout(group_layout)
        layout.addWidget(group)
        
        # Výstup
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("Název výstupu:"))
        self.merge_output = QLineEdit()
        self.merge_output.setPlaceholderText("sloučený.pdf")
        output_layout.addWidget(self.merge_output)
        layout.addLayout(output_layout)
        
        # Tlačítko sloučení
        btn_merge = QPushButton("Sloučit PDF")
        btn_merge.clicked.connect(self._merge_pdfs)
        btn_merge.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #667eea, stop:1 #764ba2);
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: bold;
            }
        """)
        layout.addWidget(btn_merge)
        
        layout.addStretch()
        return widget
    
    def _create_split_tab(self) -> QWidget:
        """Vytvoří tab pro rozdělení PDF"""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)
        
        form = QFormLayout()
        
        # Vstupní soubor
        input_layout = QHBoxLayout()
        self.split_input = QLineEdit()
        self.split_input.setReadOnly(True)
        btn_browse = QPushButton("Procházet")
        btn_browse.clicked.connect(self._browse_split_input)
        input_layout.addWidget(self.split_input)
        input_layout.addWidget(btn_browse)
        form.addRow("Vstupní PDF:", input_layout)
        
        # Info o souboru
        self.split_info = QLabel("Vyberte PDF soubor")
        form.addRow("Info:", self.split_info)
        
        # Prefix
        self.split_prefix = QLineEdit()
        self.split_prefix.setPlaceholderText("dokument")
        form.addRow("Prefix:", self.split_prefix)
        
        layout.addLayout(form)
        
        # Tlačítko
        btn_split = QPushButton("Rozdělit na stránky")
        btn_split.clicked.connect(self._split_pdf)
        layout.addWidget(btn_split)
        
        layout.addStretch()
        return widget
    
    def _create_rotate_tab(self) -> QWidget:
        """Vytvoří tab pro rotaci PDF"""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)
        
        form = QFormLayout()
        
        # Vstupní soubor
        input_layout = QHBoxLayout()
        self.rotate_input = QLineEdit()
        self.rotate_input.setReadOnly(True)
        btn_browse = QPushButton("Procházet")
        btn_browse.clicked.connect(self._browse_rotate_input)
        input_layout.addWidget(self.rotate_input)
        input_layout.addWidget(btn_browse)
        form.addRow("Vstupní PDF:", input_layout)
        
        # Rotace
        self.rotate_angle = QComboBox()
        self.rotate_angle.addItems(["90°", "180°", "270°"])
        form.addRow("Rotace:", self.rotate_angle)
        
        # Výstup
        self.rotate_output = QLineEdit()
        self.rotate_output.setPlaceholderText("otočený.pdf")
        form.addRow("Výstup:", self.rotate_output)
        
        layout.addLayout(form)
        
        # Tlačítko
        btn_rotate = QPushButton("Otočit PDF")
        btn_rotate.clicked.connect(self._rotate_pdf)
        layout.addWidget(btn_rotate)
        
        layout.addStretch()
        return widget
    
    def _create_create_tab(self) -> QWidget:
        """Vytvoří tab pro vytvoření PDF z textu"""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)
        
        layout.addWidget(QLabel("Text pro PDF:"))
        self.create_text = QTextEdit()
        self.create_text.setPlaceholderText("Zadejte text, který bude převeden do PDF...")
        layout.addWidget(self.create_text)
        
        form = QFormLayout()
        self.create_title = QLineEdit()
        self.create_title.setPlaceholderText("Dokument")
        form.addRow("Titulek:", self.create_title)
        
        self.create_output = QLineEdit()
        self.create_output.setPlaceholderText("dokument.pdf")
        form.addRow("Název souboru:", self.create_output)
        
        layout.addLayout(form)
        
        btn_create = QPushButton("Vytvořit PDF")
        btn_create.clicked.connect(self._create_pdf)
        layout.addWidget(btn_create)
        
        return widget
    
    # ============= Akce =============
    
    def _add_pdf_to_merge(self):
        """Přidá PDF do seznamu ke sloučení"""
        files, _ = QFileDialog.getOpenFileNames(
            self, "Vybrat PDF", "", "PDF soubory (*.pdf)"
        )
        for file_path in files:
            path = Path(file_path)
            self.selected_files.append(path)
            item = QListWidgetItem(path.name)
            item.setData(Qt.UserRole, str(path))
            self.merge_list.addItem(item)
    
    def _remove_pdf_from_merge(self):
        """Odebere PDF ze seznamu"""
        current = self.merge_list.currentRow()
        if current >= 0:
            self.merge_list.takeItem(current)
            self.selected_files.pop(current)
    
    def _move_up(self):
        """Přesune položku nahoru"""
        current = self.merge_list.currentRow()
        if current > 0:
            item = self.merge_list.takeItem(current)
            self.merge_list.insertItem(current - 1, item)
            self.merge_list.setCurrentRow(current - 1)
            self.selected_files[current], self.selected_files[current-1] = \
                self.selected_files[current-1], self.selected_files[current]
    
    def _move_down(self):
        """Přesune položku dolů"""
        current = self.merge_list.currentRow()
        if current < self.merge_list.count() - 1:
            item = self.merge_list.takeItem(current)
            self.merge_list.insertItem(current + 1, item)
            self.merge_list.setCurrentRow(current + 1)
            self.selected_files[current], self.selected_files[current+1] = \
                self.selected_files[current+1], self.selected_files[current]
    
    def _merge_pdfs(self):
        """Sloučí PDF soubory"""
        if not self.selected_files:
            QMessageBox.warning(self, "Chyba", "Nejsou vybrány žádné PDF soubory.")
            return
        
        output_name = self.merge_output.text().strip() or "sloučený.pdf"
        
        try:
            result = self.service.merge_pdfs(self.selected_files, output_name)
            if result:
                QMessageBox.information(
                    self, "Úspěch", f"PDF soubory byly sloučeny do:\n{result}"
                )
            else:
                QMessageBox.warning(self, "Chyba", "Nepodařilo se sloučit PDF soubory.")
        except Exception as e:
            QMessageBox.critical(self, "Chyba", f"Chyba při slučování: {str(e)}")
    
    def _browse_split_input(self):
        """Procházení pro split input"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Vybrat PDF", "", "PDF soubory (*.pdf)"
        )
        if file_path:
            self.split_input.setText(file_path)
            info = self.service.get_pdf_info(Path(file_path))
            if info:
                self.split_info.setText(f"Stránek: {info.pages}")
    
    def _split_pdf(self):
        """Rozdělí PDF"""
        input_path = self.split_input.text()
        if not input_path:
            QMessageBox.warning(self, "Chyba", "Vyberte vstupní PDF soubor.")
            return
        
        prefix = self.split_prefix.text().strip() or "dokument"
        
        try:
            results = self.service.split_pdf(Path(input_path), prefix)
            if results:
                QMessageBox.information(
                    self, "Úspěch", f"PDF bylo rozděleno na {len(results)} souborů."
                )
            else:
                QMessageBox.warning(self, "Chyba", "Nepodařilo se rozdělit PDF.")
        except Exception as e:
            QMessageBox.critical(self, "Chyba", f"Chyba při rozdělování: {str(e)}")
    
    def _browse_rotate_input(self):
        """Procházení pro rotate input"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Vybrat PDF", "", "PDF soubory (*.pdf)"
        )
        if file_path:
            self.rotate_input.setText(file_path)
    
    def _rotate_pdf(self):
        """Otočí PDF"""
        input_path = self.rotate_input.text()
        if not input_path:
            QMessageBox.warning(self, "Chyba", "Vyberte vstupní PDF soubor.")
            return
        
        rotation = int(self.rotate_angle.currentText().replace("°", ""))
        output_name = self.rotate_output.text().strip() or "otočený.pdf"
        
        try:
            result = self.service.rotate_pages(Path(input_path), rotation, output_name)
            if result:
                QMessageBox.information(
                    self, "Úspěch", f"PDF bylo otočeno a uloženo do:\n{result}"
                )
            else:
                QMessageBox.warning(self, "Chyba", "Nepodařilo se otočit PDF.")
        except Exception as e:
            QMessageBox.critical(self, "Chyba", f"Chyba při rotaci: {str(e)}")
    
    def _create_pdf(self):
        """Vytvoří PDF z textu"""
        text = self.create_text.toPlainText()
        if not text:
            QMessageBox.warning(self, "Chyba", "Zadejte text pro PDF.")
            return
        
        title = self.create_title.text().strip() or "Dokument"
        output_name = self.create_output.text().strip() or "dokument.pdf"
        
        try:
            result = self.service.create_text_pdf(text, output_name, title)
            if result:
                QMessageBox.information(
                    self, "Úspěch", f"PDF bylo vytvořeno:\n{result}"
                )
            else:
                QMessageBox.warning(self, "Chyba", "Nepodařilo se vytvořit PDF.")
        except Exception as e:
            QMessageBox.critical(self, "Chyba", f"Chyba při vytváření: {str(e)}")






