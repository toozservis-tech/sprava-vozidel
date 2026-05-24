from __future__ import annotations

from datetime import date
from typing import Optional, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QDialog,
    QFormLayout,
    QLineEdit,
    QDialogButtonBox,
    QMessageBox,
    QSplitter,
    QLabel,
    QScrollArea,
)

from .service import VehicleHubService, Vehicle


class AddVehicleDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Přidat vozidlo")

        self.vin_input = QLineEdit()
        self.plate_input = QLineEdit()
        self.name_input = QLineEdit()
        self.brand_input = QLineEdit()
        self.model_input = QLineEdit()
        self.year_input = QLineEdit()
        self.engine_input = QLineEdit()
        self.notes_input = QLineEdit()

        # Automatické doplňování při délce VIN == 17
        self.vin_input.textChanged.connect(self.on_vin_changed)

        form = QFormLayout()
        form.addRow("VIN:", self.vin_input)
        form.addRow("SPZ:", self.plate_input)
        form.addRow("Název vozidla:", self.name_input)
        form.addRow("Značka:", self.brand_input)
        form.addRow("Model:", self.model_input)
        form.addRow("Rok:", self.year_input)
        form.addRow("Motor:", self.engine_input)
        form.addRow("Poznámka:", self.notes_input)

        # Tlačítko pro načtení VIN
        btn_load_vin = QPushButton("Načíst VIN")
        btn_load_vin.clicked.connect(self.on_load_vin_clicked)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(btn_load_vin)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def on_vin_changed(self, text: str) -> None:
        """Automatické doplňování při délce VIN == 17"""
        if len(text.strip()) == 17:
            self.load_vin_data()

    def on_load_vin_clicked(self) -> None:
        """Handler pro tlačítko Načíst VIN"""
        self.load_vin_data()

    def load_vin_data(self) -> None:
        """Načte data z VIN a vyplní pole"""
        vin = self.vin_input.text().strip()
        if not vin:
            QMessageBox.warning(self, "Chybí VIN", "Zadejte prosím VIN kód.")
            return

        try:
            # Získání service z dialogu
            # Service je v parent widgetu (VehicleHubWidget)
            parent_widget = self.parent()
            if parent_widget is None or not hasattr(parent_widget, 'service'):
                QMessageBox.critical(
                    self, "Chyba", "Nelze získat přístup k service."
                )
                return

            # Volání decode_vin
            data = parent_widget.service.decode_vin(vin)

            # Vyplnění polí
            if "brand" in data and data["brand"]:
                self.brand_input.setText(str(data["brand"]))
            if "model" in data and data["model"]:
                self.model_input.setText(str(data["model"]))
            if "year" in data and data["year"]:
                self.year_input.setText(str(data["year"]))
            if "engine" in data and data["engine"]:
                self.engine_input.setText(str(data["engine"]))

            # Zpracování pneumatik
            notes_parts = []
            if self.notes_input.text().strip():
                notes_parts.append(self.notes_input.text().strip())

            if "tyres" in data and data["tyres"]:
                tyres_text = ", ".join(data["tyres"])
                notes_parts.append(f"Pneumatiky: {tyres_text}")

            if notes_parts:
                self.notes_input.setText(" | ".join(notes_parts))

        except ValueError as e:
            QMessageBox.warning(self, "Neplatné VIN", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Chyba", f"Nepodařilo se načíst data z VIN:\n{str(e)}")

    def get_data(self) -> Optional[Vehicle]:
        vin = self.vin_input.text().strip()
        plate = self.plate_input.text().strip()
        name = self.name_input.text().strip()

        if not vin or not plate or not name:
            return None

        # Parsování roku (může být prázdný nebo neplatný)
        year = None
        year_text = self.year_input.text().strip()
        if year_text:
            try:
                year = int(year_text)
            except ValueError:
                pass  # Neplatný rok, ponecháme None

        return Vehicle(
            vin=vin,
            plate=plate,
            name=name,
            brand=self.brand_input.text().strip() or None,
            model=self.model_input.text().strip() or None,
            year=year,
            engine=self.engine_input.text().strip() or None,
            notes=self.notes_input.text().strip() or None,
        )


class VehicleHubWidget(QWidget):
    """
    GUI wrapper kolem VehicleHubService.

    Vlevo v hlavním okně bude přepínač na tento widget.
    """

    def __init__(self, parent: Optional[QWidget] = None, auth_service=None, user_email: Optional[str] = None) -> None:
        super().__init__(parent)

        self.auth_service = auth_service
        self.service = VehicleHubService(user_email=user_email)

        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # ---------- HORNÍ LIŠTA ----------
        top_bar = QHBoxLayout()
        self.btn_add_vehicle = QPushButton("Přidat vozidlo")
        self.btn_add_vehicle.clicked.connect(self.on_add_vehicle_clicked)
        top_bar.addWidget(self.btn_add_vehicle)
        top_bar.addStretch()

        main_layout.addLayout(top_bar)

        # ---------- TABULKA VOZIDEL ----------
        self.table = QTableWidget(0, 5, self)
        self.table.setHorizontalHeaderLabels(["VIN", "SPZ", "Název", "Rok", "Motor"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.itemSelectionChanged.connect(self.on_table_selection_changed)

        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)

        main_layout.addWidget(self.table, stretch=1)

        # ---------- DETAIL VOZIDLA - Splitter s MDČR daty a servisními úkony ----------
        splitter = QSplitter(Qt.Horizontal)
        
        # Levý panel - MDČR data
        mdcr_panel = QWidget()
        mdcr_layout = QVBoxLayout()
        mdcr_label = QLabel("<b>Přehled z MDČR</b>")
        mdcr_layout.addWidget(mdcr_label)
        self.mdcr_details = QTextEdit()
        self.mdcr_details.setReadOnly(True)
        self.mdcr_details.setPlaceholderText("Detaily vozidla z MDČR…")
        mdcr_layout.addWidget(self.mdcr_details)
        mdcr_panel.setLayout(mdcr_layout)
        splitter.addWidget(mdcr_panel)
        
        # Pravý panel - Servisní úkony
        service_panel = QWidget()
        service_layout = QVBoxLayout()
        service_label = QLabel("<b>Servisní úkony</b>")
        service_layout.addWidget(service_label)
        self.service_details = QTextEdit()
        self.service_details.setReadOnly(True)
        self.service_details.setPlaceholderText("Servisní záznamy…")
        service_layout.addWidget(self.service_details)
        service_panel.setLayout(service_layout)
        splitter.addWidget(service_panel)
        
        splitter.setSizes([400, 400])  # Rovnoměrné rozdělení
        main_layout.addWidget(splitter, stretch=1)

        # na začátku refresh (prázdný)
        self.refresh_table()

    # ==========================
    #   AKCE
    # ==========================

    def on_add_vehicle_clicked(self) -> None:
        dlg = AddVehicleDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return

        vehicle = dlg.get_data()
        if vehicle is None:
            QMessageBox.warning(
                self,
                "Chybí údaje",
                "Vyplň prosím VIN, SPZ a název vozidla.",
            )
            return

        try:
            self.service.add_vehicle(vehicle)
        except Exception as exc:  # nechci tady řešit konkrétní typy
            QMessageBox.critical(self, "Chyba", f"Nepodařilo se uložit vozidlo:\n{exc}")
            return

        self.refresh_table()

    def on_table_selection_changed(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            self.mdcr_details.clear()
            self.service_details.clear()
            return

        vin_item = self.table.item(row, 0)
        if vin_item is None:
            self.mdcr_details.clear()
            self.service_details.clear()
            return

        vin = vin_item.text()
        vehicle = self.service.get_vehicle(vin)
        if vehicle is None:
            self.mdcr_details.setText("Vozidlo nenalezeno.")
            self.service_details.clear()
            return

        # Načíst MDČR data pro VIN
        mdcr_data = self._load_mdcr_data(vin)
        
        # Zobrazit MDČR data v levém panelu
        self.mdcr_details.setPlainText(self._format_mdcr_details(vehicle, mdcr_data))
        
        # Zobrazit servisní úkony v pravém panelu
        records = self.service.get_records_for_vehicle(vin)
        self.service_details.setPlainText(self._format_service_records(vehicle, records))

    # ==========================
    #   POMOCNÉ METODY
    # ==========================

    def refresh_table(self) -> None:
        vehicles = self.service.get_all_vehicles()
        self.table.setRowCount(len(vehicles))

        for row, v in enumerate(vehicles):
            self.table.setItem(row, 0, QTableWidgetItem(v.vin))
            self.table.setItem(row, 1, QTableWidgetItem(v.plate))
            self.table.setItem(row, 2, QTableWidgetItem(v.name))
            self.table.setItem(
                row, 3, QTableWidgetItem(str(v.year) if v.year is not None else "")
            )
            self.table.setItem(
                row, 4, QTableWidgetItem(v.engine if v.engine is not None else "")
            )

        if vehicles:
            self.table.selectRow(0)

    def _load_mdcr_data(self, vin: str) -> Optional[dict]:
        """Načte data z MDČR pro VIN"""
        try:
            # Použít service přímo
            return self.service.decode_vin(vin)
        except Exception as e:
            print(f"Chyba při načítání MDČR dat: {e}")
            return None

    @staticmethod
    def _format_mdcr_details(vehicle: Vehicle, mdcr_data: Optional[dict]) -> str:
        """Formátuje MDČR data pro zobrazení"""
        lines = [
            "Základní údaje:",
            f"VIN: {vehicle.vin}",
            f"SPZ: {vehicle.plate}",
            f"Název: {vehicle.name}",
            "",
        ]

        if vehicle.brand:
            lines.append(f"Značka: {vehicle.brand}")
        if vehicle.model:
            lines.append(f"Model: {vehicle.model}")
        if vehicle.year:
            lines.append(f"Rok výroby: {vehicle.year}")
        if vehicle.engine:
            lines.append(f"Motor: {vehicle.engine}")
        
        if mdcr_data:
            lines.append("")
            lines.append("Data z MDČR:")
            if "brand" in mdcr_data and mdcr_data["brand"]:
                lines.append(f"Značka: {mdcr_data['brand']}")
            if "model" in mdcr_data and mdcr_data["model"]:
                lines.append(f"Model: {mdcr_data['model']}")
            if "year" in mdcr_data and mdcr_data["year"]:
                lines.append(f"Rok: {mdcr_data['year']}")
            if "engine" in mdcr_data and mdcr_data["engine"]:
                lines.append(f"Motor: {mdcr_data['engine']}")
            if "tyres" in mdcr_data and mdcr_data["tyres"]:
                lines.append("")
                lines.append("Pneumatiky:")
                for tyre in mdcr_data["tyres"]:
                    lines.append(f"  • {tyre}")
        
        if vehicle.notes:
            lines.append("")
            lines.append("Poznámka:")
            lines.append(vehicle.notes)

        return "\n".join(lines)
    
    @staticmethod
    def _format_service_records(vehicle: Vehicle, records: List) -> str:
        """Formátuje servisní záznamy pro zobrazení"""
        if not records:
            return "Žádné servisní záznamy."
        
        lines = [f"Servisní záznamy pro {vehicle.name or vehicle.vin}:", ""]
        
        for i, record in enumerate(records, 1):
            lines.append(f"Záznam #{i}")
            lines.append(f"Datum: {record.date}")
            if record.odometer_km:
                lines.append(f"Najeto: {record.odometer_km} km")
            lines.append(f"Popis: {record.description}")
            if record.category:
                lines.append(f"Kategorie: {record.category}")
            if record.price:
                lines.append(f"Cena: {record.price} Kč")
        lines.append("")

        return "\n".join(lines)

