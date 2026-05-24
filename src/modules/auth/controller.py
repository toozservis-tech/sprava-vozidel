from __future__ import annotations

from typing import Optional
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QDialogButtonBox,
    QMessageBox,
    QVBoxLayout,
    QLabel,
)
from PySide6.QtCore import Qt

from .service import AuthService


class LoginDialog(QDialog):
    """Dialog pro přihlášení uživatele"""
    
    def __init__(self, auth_service: AuthService, parent=None):
        super().__init__(parent)
        self.auth_service = auth_service
        self.setWindowTitle("Přihlášení")
        self.setModal(True)
        
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("email@example.com")
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Heslo")
        
        form = QFormLayout()
        form.addRow("Email:", self.email_input)
        form.addRow("Heslo:", self.password_input)
        
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self
        )
        buttons.accepted.connect(self.on_login)
        buttons.rejected.connect(self.reject)
        
        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)
    
    def on_login(self):
        email = self.email_input.text().strip()
        password = self.password_input.text()
        
        if not email or not password:
            QMessageBox.warning(self, "Chybí údaje", "Vyplňte prosím email a heslo.")
            return
        
        if self.auth_service.login(email, password):
            self.accept()
        else:
            QMessageBox.warning(self, "Chyba", "Nepodařilo se přihlásit. Zkontrolujte email a heslo.")


class RegisterDialog(QDialog):
    """Dialog pro registraci nového uživatele"""
    
    def __init__(self, auth_service: AuthService, parent=None):
        super().__init__(parent)
        self.auth_service = auth_service
        self.setWindowTitle("Registrace")
        self.setModal(True)
        
        # Přihlašovací údaje
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("email@example.com")
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_confirm_input = QLineEdit()
        self.password_confirm_input.setEchoMode(QLineEdit.Password)
        
        # Firemní údaje
        self.ico_input = QLineEdit()
        self.ico_input.setPlaceholderText("12345678")
        self.ico_input.textChanged.connect(self.on_ico_changed)
        self.last_loaded_ico = ""  # Sledování posledního načteného IČO
        
        self.name_input = QLineEdit()
        self.dic_input = QLineEdit()
        self.dic_input.setPlaceholderText("CZ12345678")
        self.street_input = QLineEdit()
        self.street_number_input = QLineEdit()
        self.street_number_input.setPlaceholderText("123")
        self.city_input = QLineEdit()
        self.zip_input = QLineEdit()
        self.phone_input = QLineEdit()
        
        # Tlačítko pro načtení z ARES
        self.btn_load_ares = QPushButton("Načíst z ARES")
        self.btn_load_ares.clicked.connect(self.on_load_ares)
        
        form = QFormLayout()
        form.addRow(QLabel("<b>Přihlašovací údaje</b>"))
        form.addRow("Email:", self.email_input)
        form.addRow("Heslo:", self.password_input)
        form.addRow("Potvrzení hesla:", self.password_confirm_input)
        
        form.addRow(QLabel(""))  # Prázdný řádek
        form.addRow(QLabel("<b>Firemní údaje</b>"))
        form.addRow("IČO:", self.ico_input)
        form.addRow("", self.btn_load_ares)
        form.addRow("Název firmy:", self.name_input)
        form.addRow("DIČ:", self.dic_input)
        form.addRow("Ulice:", self.street_input)
        form.addRow("Číslo popisné:", self.street_number_input)
        form.addRow("Město:", self.city_input)
        form.addRow("PSČ:", self.zip_input)
        form.addRow("Telefon:", self.phone_input)
        
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self
        )
        buttons.accepted.connect(self.on_register)
        buttons.rejected.connect(self.reject)
        
        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)
    
    def on_ico_changed(self, text: str):
        """Automatické načtení z ARES při zadání 8 číslic IČO"""
        ico = text.strip().replace(" ", "")
        
        # Pokud se IČO změnilo a není to stejné jako poslední načtené, vymaž pole
        if ico != self.last_loaded_ico and self.last_loaded_ico:
            # Pokud uživatel začal psát nové IČO, vymaž pole okamžitě
            # (ale ne pokud je pole prázdné - to je jen při prvním otevření)
            self.clear_ares_fields()
            self.last_loaded_ico = ""  # Reset, protože jsme vymazali pole
        
        # Automatické načtení při zadání 8 číslic
        if len(ico) == 8 and ico.isdigit() and ico != self.last_loaded_ico:
            self.load_ares_data(ico)
    
    def on_load_ares(self):
        """Handler pro tlačítko Načíst z ARES"""
        ico = self.ico_input.text().strip().replace(" ", "")
        if not ico:
            QMessageBox.warning(self, "Chybí IČO", "Zadejte prosím IČO.")
            return
        
        if len(ico) != 8 or not ico.isdigit():
            QMessageBox.warning(self, "Neplatné IČO", "IČO musí mít 8 číslic.")
            return
        
        self.load_ares_data(ico)
    
    def clear_ares_fields(self):
        """Vymaže všechna pole naplněná z ARES"""
        self.name_input.clear()
        self.dic_input.clear()
        self.street_input.clear()
        self.street_number_input.clear()
        self.city_input.clear()
        self.zip_input.clear()
        self.phone_input.clear()
    
    def load_ares_data(self, ico: str):
        """Načte data z ARES a vyplní formulář"""
        # Nejdříve vymaž všechna pole
        self.clear_ares_fields()
        
        try:
            data = self.auth_service.fetch_ares_data(ico)
            if not data:
                QMessageBox.warning(
                    self, 
                    "Chyba", 
                    "Nepodařilo se načíst data z ARES.\n\n"
                    "Možné příčiny:\n"
                    "• Backend neběží na správné adrese\n"
                    "• Neplatné IČO\n"
                    "• Problém s připojením k internetu\n\n"
                    "Zkontrolujte konzoli pro více informací."
                )
                self.last_loaded_ico = ""  # Reset při chybě
                return
            
            # Uložit načtené IČO
            self.last_loaded_ico = ico
            
            # Vyplnění polí podle odpovědi z ARES
            if "nazev" in data:
                self.name_input.setText(str(data["nazev"]))
            elif "name" in data:
                self.name_input.setText(str(data["name"]))
            
            # DIČ
            if "dic" in data:
                self.dic_input.setText(str(data["dic"]))
            elif "tax_id" in data:
                self.dic_input.setText(str(data["tax_id"]))
            
            # Ulice a číslo popisné
            if "ulice" in data:
                self.street_input.setText(str(data["ulice"]))
            elif "street" in data:
                self.street_input.setText(str(data["street"]))
            
            if "cislo_popisne" in data:
                self.street_number_input.setText(str(data["cislo_popisne"]))
            elif "street_number" in data:
                self.street_number_input.setText(str(data["street_number"]))
            elif "cisloPopisne" in data:
                self.street_number_input.setText(str(data["cisloPopisne"]))
            
            if "mesto" in data:
                self.city_input.setText(str(data["mesto"]))
            elif "city" in data:
                self.city_input.setText(str(data["city"]))
            
            if "psc" in data:
                self.zip_input.setText(str(data["psc"]))
            elif "zip" in data:
                self.zip_input.setText(str(data["zip"]))
            
            if "telefon" in data:
                self.phone_input.setText(str(data["telefon"]))
            elif "phone" in data:
                self.phone_input.setText(str(data["phone"]))
        
        except Exception as e:
            QMessageBox.critical(
                self, "Chyba", f"Nepodařilo se načíst data z ARES:\n{str(e)}"
            )
    
    def on_register(self):
        """Handler pro registraci"""
        email = self.email_input.text().strip()
        password = self.password_input.text()
        password_confirm = self.password_confirm_input.text()
        
        if not email:
            QMessageBox.warning(self, "Chybí údaje", "Zadejte prosím email.")
            return
        
        if not password:
            QMessageBox.warning(self, "Chybí údaje", "Zadejte prosím heslo.")
            return
        
        if password != password_confirm:
            QMessageBox.warning(self, "Chyba", "Hesla se neshodují.")
            return
        
        customer_data = {
            "name": self.name_input.text().strip() or None,
            "ico": self.ico_input.text().strip() or None,
            "dic": self.dic_input.text().strip() or None,
            "street": self.street_input.text().strip() or None,
            "street_number": self.street_number_input.text().strip() or None,
            "city": self.city_input.text().strip() or None,
            "zip": self.zip_input.text().strip() or None,
            "phone": self.phone_input.text().strip() or None,
        }
        
        if self.auth_service.register(email, password, customer_data):
            QMessageBox.information(
                self, "Úspěch", "Registrace proběhla úspěšně. Nyní se můžete přihlásit."
            )
            self.accept()
        else:
            QMessageBox.warning(
                self, "Chyba", "Nepodařilo se zaregistrovat. Zkuste to prosím znovu."
            )

