"""
Správa vozidel – hlavní desktop aplikace (legacy Qt shell).
"""
import sys
from pathlib import Path

# Přidání kořenového adresáře projektu do Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QStackedWidget,
    QLabel,
    QMessageBox,
    QDialog,
    QFrame,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from src.modules.auth.service import AuthService
from src.modules.auth.controller import LoginDialog, RegisterDialog
from src.modules.vehicle_hub.controller import VehicleHubWidget
from src.modules.email_client.controller import EmailClientWidget
from src.modules.pdf_manager.controller import PDFManagerWidget
from src.modules.image_tools.controller import ImageToolsWidget
from src.modules.voice.controller import VoiceWidget


class SidebarButton(QPushButton):
    """Stylizované tlačítko pro sidebar"""
    
    def __init__(self, text: str, icon: str = "", parent=None):
        super().__init__(f"{icon}  {text}" if icon else text, parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(45)
        self.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 8px;
                padding: 10px 15px;
                text-align: left;
                font-size: 14px;
                color: #333;
            }
            QPushButton:hover {
                background: rgba(102, 126, 234, 0.1);
            }
            QPushButton:checked {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                color: white;
                font-weight: bold;
            }
        """)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("Správa vozidel")
        self.setGeometry(100, 100, 1200, 800)
        self.setStyleSheet("""
            QMainWindow {
                background: #f5f6fa;
            }
        """)
        
        # Auth service
        self.auth_service = AuthService()
        
        # Zobrazit přihlašovací dialog
        if not self.show_login():
            sys.exit(0)

        self._setup_ui()

    def _setup_ui(self):
        """Nastaví hlavní UI"""
        central = QWidget(self)
        self.setCentralWidget(central)

        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        central.setLayout(main_layout)

        # ============= SIDEBAR =============
        sidebar = QFrame()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet("""
            QFrame {
                background: white;
                border-right: 1px solid #e0e0e0;
            }
        """)
        
        sidebar_layout = QVBoxLayout()
        sidebar_layout.setContentsMargins(10, 15, 10, 15)
        sidebar_layout.setSpacing(5)
        sidebar.setLayout(sidebar_layout)
        
        # Logo/Header
        header = QLabel("🚗 Správa vozidel")
        header.setFont(QFont("Arial", 18, QFont.Bold))
        header.setStyleSheet("color: #667eea; padding: 10px;")
        sidebar_layout.addWidget(header)
        
        # User info
        user_email = self.auth_service.get_current_user_email() or "Uživatel"
        user_label = QLabel(f"👤 {user_email}")
        user_label.setStyleSheet("color: #666; font-size: 11px; padding: 5px 10px;")
        user_label.setWordWrap(True)
        sidebar_layout.addWidget(user_label)
        
        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background: #e0e0e0;")
        sidebar_layout.addWidget(sep)
        sidebar_layout.addSpacing(10)

        # Menu buttons
        buttons_info = [
            ("Vehicle Hub", "🚗", 0),
            ("Email", "📧", 1),
            ("PDF Nástroje", "📄", 2),
            ("Obrázky", "🖼️", 3),
            ("Hlas", "🎤", 4),
            ("Nastavení", "⚙️", 5),
        ]

        self.menu_buttons = {}
        for text, icon, index in buttons_info:
            btn = SidebarButton(text, icon)
            btn.clicked.connect(lambda checked, i=index: self._switch_page(i))
            sidebar_layout.addWidget(btn)
            self.menu_buttons[index] = btn

        sidebar_layout.addStretch()
        
        # Logout button
        btn_logout = QPushButton("🚪 Odhlásit se")
        btn_logout.setCursor(Qt.PointingHandCursor)
        btn_logout.clicked.connect(self.on_logout)
        btn_logout.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 1px solid #dc3545;
                border-radius: 6px;
                padding: 8px;
                color: #dc3545;
            }
            QPushButton:hover {
                background: #dc3545;
                color: white;
            }
        """)
        sidebar_layout.addWidget(btn_logout)

        # ============= CONTENT AREA =============
        content_area = QFrame()
        content_area.setStyleSheet("background: #f5f6fa;")
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_area.setLayout(content_layout)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet("""
            QStackedWidget {
                background: white;
                border-radius: 12px;
            }
        """)

        # Vytvoření stránek
        user_email = self.auth_service.get_current_user_email()
        
        # 0: Vehicle Hub
        self.page_vehicle = VehicleHubWidget(auth_service=self.auth_service, user_email=user_email)
        
        # 1: Email
        self.page_email = EmailClientWidget()
        
        # 2: PDF
        self.page_pdf = PDFManagerWidget()
        
        # 3: Obrázky
        self.page_images = ImageToolsWidget()
        
        # 4: Hlas
        self.page_voice = VoiceWidget()
        
        # 5: Nastavení
        self.page_settings = self._create_settings_page()

        pages = [
            self.page_vehicle,
            self.page_email,
            self.page_pdf,
            self.page_images,
            self.page_voice,
            self.page_settings,
        ]

        for p in pages:
            container = QWidget()
            container_layout = QVBoxLayout()
            container_layout.setContentsMargins(15, 15, 15, 15)
            container_layout.addWidget(p)
            container.setLayout(container_layout)
            self.stack.addWidget(container)

        content_layout.addWidget(self.stack)

        # ============= LAYOUT =============
        main_layout.addWidget(sidebar)
        main_layout.addWidget(content_area, 1)
        
        # Výchozí stránka
        self._switch_page(0)

    def _switch_page(self, index: int):
        """Přepne na zadanou stránku"""
        self.stack.setCurrentIndex(index)
        
        # Aktualizovat stav tlačítek
        for i, btn in self.menu_buttons.items():
            btn.setChecked(i == index)

    def _create_settings_page(self) -> QWidget:
        """Vytvoří stránku nastavení"""
        page = QWidget()
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignTop)
        
        title = QLabel("⚙️ Nastavení")
        title.setFont(QFont("Arial", 20, QFont.Bold))
        title.setStyleSheet("color: #333; margin-bottom: 20px;")
        layout.addWidget(title)
        
        # Info o aplikaci
        info_group = QFrame()
        info_group.setStyleSheet("""
            QFrame {
                background: #f8f9fa;
                border-radius: 8px;
                padding: 15px;
            }
        """)
        info_layout = QVBoxLayout()
        info_group.setLayout(info_layout)
        
        info_layout.addWidget(QLabel("<b>Správa vozidel</b>"))
        info_layout.addWidget(QLabel("Verze: 2.0.0"))
        info_layout.addWidget(QLabel(f"Uživatel: {self.auth_service.get_current_user_email() or 'Nepřihlášen'}"))
        
        from src.core.config import BASE_API_URL, ENVIRONMENT
        info_layout.addWidget(QLabel(f"API URL: {BASE_API_URL}"))
        info_layout.addWidget(QLabel(f"Prostředí: {ENVIRONMENT}"))
        
        layout.addWidget(info_group)
        
        # Funkcionalita
        features_label = QLabel("<b>Dostupné funkce:</b>")
        features_label.setStyleSheet("margin-top: 20px;")
        layout.addWidget(features_label)
        
        features = [
            "✅ Vehicle Hub - správa vozidel, VIN dekodér",
            "✅ Email - odesílání emailů",
            "✅ PDF Nástroje - sloučení, rozdělení, rotace PDF",
            "✅ Obrázky - úprava, filtry, konverze",
            "⚠️ Hlas - vyžaduje dodatečné knihovny",
        ]
        
        for feature in features:
            layout.addWidget(QLabel(feature))
        
        layout.addStretch()
        page.setLayout(layout)
        return page

    def show_login(self) -> bool:
        """Zobrazí přihlašovací dialog. Vrací True pokud se uživatel přihlásil."""
        dialog = LoginDialog(self.auth_service, self)
        
        register_btn = QPushButton("Registrace")
        register_btn.clicked.connect(lambda: self.show_register(dialog))
        dialog.layout().insertWidget(0, register_btn)
        
        if dialog.exec() == QDialog.Accepted:
            return True
        return False
    
    def show_register(self, login_dialog):
        """Zobrazí registrační dialog"""
        login_dialog.reject()
        dialog = RegisterDialog(self.auth_service, self)
        if dialog.exec() == QDialog.Accepted:
            if self.show_login():
                self._reinit_window()
            else:
                sys.exit(0)
    
    def _reinit_window(self):
        """Reinicializuje okno s novým uživatelem"""
        try:
            self.close()
            window = MainWindow()
            window.show()
        except Exception as e:
            print(f"Chyba při reinicializaci okna: {e}")
            sys.exit(1)
    
    def on_logout(self):
        """Odhlásí uživatele"""
        reply = QMessageBox.question(
            self, "Odhlášení", "Opravdu se chcete odhlásit?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.auth_service.logout()
            self.close()
            window = MainWindow()
            window.show()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Nastavení stylu aplikace
    app.setStyle("Fusion")
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
