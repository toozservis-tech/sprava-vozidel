"""
Image Tools Controller - GUI widget pro práci s obrázky
"""
from __future__ import annotations

from typing import Optional
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
    QLineEdit,
    QSpinBox,
    QComboBox,
    QSlider,
    QTabWidget,
    QFormLayout,
    QCheckBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

from .service import ImageService


class ImageToolsWidget(QWidget):
    """Widget pro práci s obrázky"""
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.service = ImageService()
        self.current_image: Optional[Path] = None
        self._setup_ui()
    
    def _setup_ui(self):
        """Nastaví UI komponenty"""
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Status
        self.status_label = QLabel()
        self._update_status()
        layout.addWidget(self.status_label)
        
        # Výběr obrázku
        select_layout = QHBoxLayout()
        self.image_path_input = QLineEdit()
        self.image_path_input.setReadOnly(True)
        self.image_path_input.setPlaceholderText("Vyberte obrázek...")
        btn_browse = QPushButton("Procházet")
        btn_browse.clicked.connect(self._browse_image)
        select_layout.addWidget(self.image_path_input)
        select_layout.addWidget(btn_browse)
        layout.addLayout(select_layout)
        
        # Info o obrázku
        self.image_info = QLabel("Není vybrán žádný obrázek")
        layout.addWidget(self.image_info)
        
        # Náhled
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumHeight(150)
        self.preview_label.setStyleSheet("background: #f0f0f0; border: 1px solid #ccc;")
        layout.addWidget(self.preview_label)
        
        # Tab widget pro nástroje
        tabs = QTabWidget()
        
        tabs.addTab(self._create_resize_tab(), "Změna velikosti")
        tabs.addTab(self._create_rotate_tab(), "Rotace/Převrácení")
        tabs.addTab(self._create_filter_tab(), "Filtry")
        tabs.addTab(self._create_convert_tab(), "Konverze")
        
        layout.addWidget(tabs)
    
    def _update_status(self):
        """Aktualizuje status"""
        if self.service.is_available():
            self.status_label.setText("✅ Nástroje pro obrázky jsou k dispozici")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.status_label.setText("⚠️ Pillow není nainstalován. Spusťte: pip install Pillow")
            self.status_label.setStyleSheet("color: orange; font-weight: bold;")
    
    def _browse_image(self):
        """Procházení pro výběr obrázku"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Vybrat obrázek", "",
            "Obrázky (*.png *.jpg *.jpeg *.gif *.bmp *.webp);;Všechny soubory (*.*)"
        )
        if file_path:
            self.current_image = Path(file_path)
            self.image_path_input.setText(file_path)
            self._update_preview()
    
    def _update_preview(self):
        """Aktualizuje náhled obrázku"""
        if not self.current_image or not self.current_image.exists():
            self.preview_label.setText("Není vybrán žádný obrázek")
            self.image_info.setText("")
            return
        
        # Zobrazit info
        info = self.service.get_image_info(self.current_image)
        if info:
            size_kb = info.size_bytes / 1024
            self.image_info.setText(
                f"Rozměry: {info.width}×{info.height} | "
                f"Formát: {info.format} | "
                f"Režim: {info.mode} | "
                f"Velikost: {size_kb:.1f} KB"
            )
        
        # Zobrazit náhled
        pixmap = QPixmap(str(self.current_image))
        if not pixmap.isNull():
            scaled = pixmap.scaled(
                300, 200,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.preview_label.setPixmap(scaled)
    
    def _create_resize_tab(self) -> QWidget:
        """Vytvoří tab pro změnu velikosti"""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)
        
        form = QFormLayout()
        
        self.resize_width = QSpinBox()
        self.resize_width.setRange(1, 10000)
        self.resize_width.setValue(800)
        form.addRow("Šířka:", self.resize_width)
        
        self.resize_height = QSpinBox()
        self.resize_height.setRange(1, 10000)
        self.resize_height.setValue(600)
        form.addRow("Výška:", self.resize_height)
        
        self.keep_aspect = QCheckBox("Zachovat poměr stran")
        self.keep_aspect.setChecked(True)
        form.addRow("", self.keep_aspect)
        
        self.resize_output = QLineEdit()
        self.resize_output.setPlaceholderText("resized.png")
        form.addRow("Výstup:", self.resize_output)
        
        layout.addLayout(form)
        
        btn = QPushButton("Změnit velikost")
        btn.clicked.connect(self._resize_image)
        layout.addWidget(btn)
        
        layout.addStretch()
        return widget
    
    def _create_rotate_tab(self) -> QWidget:
        """Vytvoří tab pro rotaci"""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)
        
        # Rotace
        rotate_group = QGroupBox("Rotace")
        rotate_layout = QFormLayout()
        
        self.rotate_angle = QComboBox()
        self.rotate_angle.addItems(["90°", "180°", "270°", "Vlastní"])
        rotate_layout.addRow("Úhel:", self.rotate_angle)
        
        self.custom_angle = QSpinBox()
        self.custom_angle.setRange(-360, 360)
        self.custom_angle.setValue(45)
        rotate_layout.addRow("Vlastní úhel:", self.custom_angle)
        
        self.rotate_output = QLineEdit()
        self.rotate_output.setPlaceholderText("rotated.png")
        rotate_layout.addRow("Výstup:", self.rotate_output)
        
        rotate_group.setLayout(rotate_layout)
        layout.addWidget(rotate_group)
        
        btn_rotate = QPushButton("Otočit")
        btn_rotate.clicked.connect(self._rotate_image)
        layout.addWidget(btn_rotate)
        
        # Převrácení
        flip_group = QGroupBox("Převrácení")
        flip_layout = QHBoxLayout()
        
        btn_flip_h = QPushButton("↔ Horizontálně")
        btn_flip_h.clicked.connect(lambda: self._flip_image("horizontal"))
        btn_flip_v = QPushButton("↕ Vertikálně")
        btn_flip_v.clicked.connect(lambda: self._flip_image("vertical"))
        
        flip_layout.addWidget(btn_flip_h)
        flip_layout.addWidget(btn_flip_v)
        flip_group.setLayout(flip_layout)
        layout.addWidget(flip_group)
        
        layout.addStretch()
        return widget
    
    def _create_filter_tab(self) -> QWidget:
        """Vytvoří tab pro filtry"""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)
        
        form = QFormLayout()
        
        self.filter_type = QComboBox()
        self.filter_type.addItems([
            "grayscale (Šedá)",
            "blur (Rozmazání)",
            "sharpen (Zostření)",
            "contour (Kontury)",
            "edge_enhance (Vylepšení hran)",
            "emboss (Reliéf)",
            "smooth (Vyhlazení)"
        ])
        form.addRow("Filtr:", self.filter_type)
        
        self.filter_output = QLineEdit()
        self.filter_output.setPlaceholderText("filtered.png")
        form.addRow("Výstup:", self.filter_output)
        
        layout.addLayout(form)
        
        btn = QPushButton("Aplikovat filtr")
        btn.clicked.connect(self._apply_filter)
        layout.addWidget(btn)
        
        # Jas
        brightness_group = QGroupBox("Jas")
        brightness_layout = QVBoxLayout()
        
        self.brightness_slider = QSlider(Qt.Horizontal)
        self.brightness_slider.setRange(0, 200)
        self.brightness_slider.setValue(100)
        self.brightness_label = QLabel("100%")
        self.brightness_slider.valueChanged.connect(
            lambda v: self.brightness_label.setText(f"{v}%")
        )
        
        brightness_layout.addWidget(self.brightness_slider)
        brightness_layout.addWidget(self.brightness_label)
        
        btn_brightness = QPushButton("Upravit jas")
        btn_brightness.clicked.connect(self._adjust_brightness)
        brightness_layout.addWidget(btn_brightness)
        
        brightness_group.setLayout(brightness_layout)
        layout.addWidget(brightness_group)
        
        layout.addStretch()
        return widget
    
    def _create_convert_tab(self) -> QWidget:
        """Vytvoří tab pro konverzi"""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)
        
        form = QFormLayout()
        
        self.convert_format = QComboBox()
        self.convert_format.addItems(["PNG", "JPEG", "BMP", "GIF", "WEBP"])
        form.addRow("Formát:", self.convert_format)
        
        self.convert_output = QLineEdit()
        self.convert_output.setPlaceholderText("converted.png")
        form.addRow("Výstup:", self.convert_output)
        
        layout.addLayout(form)
        
        btn = QPushButton("Konvertovat")
        btn.clicked.connect(self._convert_image)
        layout.addWidget(btn)
        
        layout.addStretch()
        return widget
    
    # ============= Akce =============
    
    def _check_image_selected(self) -> bool:
        """Zkontroluje, zda je vybrán obrázek"""
        if not self.current_image or not self.current_image.exists():
            QMessageBox.warning(self, "Chyba", "Nejprve vyberte obrázek.")
            return False
        return True
    
    def _resize_image(self):
        """Změní velikost obrázku"""
        if not self._check_image_selected():
            return
        
        output = self.resize_output.text().strip() or "resized.png"
        
        try:
            result = self.service.resize_image(
                self.current_image,
                self.resize_width.value(),
                self.resize_height.value(),
                output,
                self.keep_aspect.isChecked()
            )
            if result:
                QMessageBox.information(self, "Úspěch", f"Obrázek uložen:\n{result}")
        except Exception as e:
            QMessageBox.critical(self, "Chyba", f"Chyba: {str(e)}")
    
    def _rotate_image(self):
        """Otočí obrázek"""
        if not self._check_image_selected():
            return
        
        angle_text = self.rotate_angle.currentText()
        if angle_text == "Vlastní":
            angle = self.custom_angle.value()
        else:
            angle = int(angle_text.replace("°", ""))
        
        output = self.rotate_output.text().strip() or "rotated.png"
        
        try:
            result = self.service.rotate_image(self.current_image, angle, output)
            if result:
                QMessageBox.information(self, "Úspěch", f"Obrázek uložen:\n{result}")
        except Exception as e:
            QMessageBox.critical(self, "Chyba", f"Chyba: {str(e)}")
    
    def _flip_image(self, direction: str):
        """Převrátí obrázek"""
        if not self._check_image_selected():
            return
        
        output = f"flipped_{direction}.png"
        
        try:
            result = self.service.flip_image(self.current_image, direction, output)
            if result:
                QMessageBox.information(self, "Úspěch", f"Obrázek uložen:\n{result}")
        except Exception as e:
            QMessageBox.critical(self, "Chyba", f"Chyba: {str(e)}")
    
    def _apply_filter(self):
        """Aplikuje filtr"""
        if not self._check_image_selected():
            return
        
        filter_name = self.filter_type.currentText().split(" ")[0]
        output = self.filter_output.text().strip() or "filtered.png"
        
        try:
            result = self.service.apply_filter(self.current_image, filter_name, output)
            if result:
                QMessageBox.information(self, "Úspěch", f"Obrázek uložen:\n{result}")
        except Exception as e:
            QMessageBox.critical(self, "Chyba", f"Chyba: {str(e)}")
    
    def _adjust_brightness(self):
        """Upraví jas"""
        if not self._check_image_selected():
            return
        
        factor = self.brightness_slider.value() / 100.0
        output = "brightness_adjusted.png"
        
        try:
            result = self.service.adjust_brightness(self.current_image, factor, output)
            if result:
                QMessageBox.information(self, "Úspěch", f"Obrázek uložen:\n{result}")
        except Exception as e:
            QMessageBox.critical(self, "Chyba", f"Chyba: {str(e)}")
    
    def _convert_image(self):
        """Konvertuje formát"""
        if not self._check_image_selected():
            return
        
        fmt = self.convert_format.currentText()
        output = self.convert_output.text().strip() or f"converted.{fmt.lower()}"
        
        try:
            result = self.service.convert_format(self.current_image, fmt, output)
            if result:
                QMessageBox.information(self, "Úspěch", f"Obrázek uložen:\n{result}")
        except Exception as e:
            QMessageBox.critical(self, "Chyba", f"Chyba: {str(e)}")






