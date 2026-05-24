"""
PDF Manager Service - služba pro práci s PDF soubory
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass

# Pokusit se importovat PDF knihovny
try:
    from PyPDF2 import PdfReader, PdfWriter, PdfMerger
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

from src.core.config import PDF_DIR


@dataclass
class PDFInfo:
    """Informace o PDF souboru"""
    path: Path
    pages: int
    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    creator: Optional[str] = None


class PDFService:
    """Služba pro práci s PDF soubory"""
    
    def __init__(self):
        self.output_dir = PDF_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def is_available(self) -> bool:
        """Zkontroluje, zda jsou dostupné PDF knihovny"""
        return PYPDF2_AVAILABLE
    
    def get_pdf_info(self, pdf_path: Path) -> Optional[PDFInfo]:
        """
        Získá informace o PDF souboru.
        
        Args:
            pdf_path: Cesta k PDF souboru
            
        Returns:
            PDFInfo objekt nebo None pokud soubor nelze přečíst
        """
        if not PYPDF2_AVAILABLE:
            return None
        
        if not pdf_path.exists():
            return None
        
        try:
            reader = PdfReader(str(pdf_path))
            metadata = reader.metadata or {}
            
            return PDFInfo(
                path=pdf_path,
                pages=len(reader.pages),
                title=metadata.get("/Title"),
                author=metadata.get("/Author"),
                subject=metadata.get("/Subject"),
                creator=metadata.get("/Creator")
            )
        except Exception as e:
            print(f"[PDF] Chyba při čtení PDF: {e}")
            return None
    
    def merge_pdfs(self, pdf_paths: List[Path], output_name: str) -> Optional[Path]:
        """
        Sloučí více PDF souborů do jednoho.
        
        Args:
            pdf_paths: Seznam cest k PDF souborům
            output_name: Název výstupního souboru
            
        Returns:
            Cesta k výslednému PDF nebo None při chybě
        """
        if not PYPDF2_AVAILABLE:
            raise RuntimeError("PyPDF2 není nainstalován")
        
        if not pdf_paths:
            return None
        
        output_path = self.output_dir / output_name
        if not output_path.suffix.lower() == ".pdf":
            output_path = output_path.with_suffix(".pdf")
        
        try:
            merger = PdfMerger()
            
            for pdf_path in pdf_paths:
                if pdf_path.exists():
                    merger.append(str(pdf_path))
            
            merger.write(str(output_path))
            merger.close()
            
            return output_path
        except Exception as e:
            print(f"[PDF] Chyba při slučování PDF: {e}")
            return None
    
    def split_pdf(self, pdf_path: Path, output_prefix: str) -> List[Path]:
        """
        Rozdělí PDF na jednotlivé stránky.
        
        Args:
            pdf_path: Cesta k PDF souboru
            output_prefix: Prefix pro názvy výstupních souborů
            
        Returns:
            Seznam cest k výsledným PDF souborům
        """
        if not PYPDF2_AVAILABLE:
            raise RuntimeError("PyPDF2 není nainstalován")
        
        if not pdf_path.exists():
            return []
        
        result_paths = []
        
        try:
            reader = PdfReader(str(pdf_path))
            
            for i, page in enumerate(reader.pages, 1):
                writer = PdfWriter()
                writer.add_page(page)
                
                output_path = self.output_dir / f"{output_prefix}_page_{i:03d}.pdf"
                with open(output_path, "wb") as f:
                    writer.write(f)
                
                result_paths.append(output_path)
            
            return result_paths
        except Exception as e:
            print(f"[PDF] Chyba při rozdělování PDF: {e}")
            return []
    
    def extract_pages(
        self, 
        pdf_path: Path, 
        page_numbers: List[int], 
        output_name: str
    ) -> Optional[Path]:
        """
        Extrahuje vybrané stránky z PDF.
        
        Args:
            pdf_path: Cesta k PDF souboru
            page_numbers: Seznam čísel stránek (1-indexed)
            output_name: Název výstupního souboru
            
        Returns:
            Cesta k výslednému PDF nebo None při chybě
        """
        if not PYPDF2_AVAILABLE:
            raise RuntimeError("PyPDF2 není nainstalován")
        
        if not pdf_path.exists():
            return None
        
        output_path = self.output_dir / output_name
        if not output_path.suffix.lower() == ".pdf":
            output_path = output_path.with_suffix(".pdf")
        
        try:
            reader = PdfReader(str(pdf_path))
            writer = PdfWriter()
            
            for page_num in page_numbers:
                # Převod na 0-indexed
                idx = page_num - 1
                if 0 <= idx < len(reader.pages):
                    writer.add_page(reader.pages[idx])
            
            with open(output_path, "wb") as f:
                writer.write(f)
            
            return output_path
        except Exception as e:
            print(f"[PDF] Chyba při extrakci stránek: {e}")
            return None
    
    def rotate_pages(
        self, 
        pdf_path: Path, 
        rotation: int, 
        output_name: str
    ) -> Optional[Path]:
        """
        Otočí všechny stránky PDF.
        
        Args:
            pdf_path: Cesta k PDF souboru
            rotation: Úhel otočení (90, 180, 270)
            output_name: Název výstupního souboru
            
        Returns:
            Cesta k výslednému PDF nebo None při chybě
        """
        if not PYPDF2_AVAILABLE:
            raise RuntimeError("PyPDF2 není nainstalován")
        
        if rotation not in [90, 180, 270]:
            raise ValueError("Rotace musí být 90, 180 nebo 270 stupňů")
        
        if not pdf_path.exists():
            return None
        
        output_path = self.output_dir / output_name
        if not output_path.suffix.lower() == ".pdf":
            output_path = output_path.with_suffix(".pdf")
        
        try:
            reader = PdfReader(str(pdf_path))
            writer = PdfWriter()
            
            for page in reader.pages:
                page.rotate(rotation)
                writer.add_page(page)
            
            with open(output_path, "wb") as f:
                writer.write(f)
            
            return output_path
        except Exception as e:
            print(f"[PDF] Chyba při rotaci PDF: {e}")
            return None
    
    def create_text_pdf(
        self, 
        text: str, 
        output_name: str, 
        title: str = "Dokument"
    ) -> Optional[Path]:
        """
        Vytvoří PDF z textu.
        
        Args:
            text: Text pro vložení do PDF
            output_name: Název výstupního souboru
            title: Titulek dokumentu
            
        Returns:
            Cesta k výslednému PDF nebo None při chybě
        """
        if not REPORTLAB_AVAILABLE:
            raise RuntimeError("ReportLab není nainstalován")
        
        output_path = self.output_dir / output_name
        if not output_path.suffix.lower() == ".pdf":
            output_path = output_path.with_suffix(".pdf")
        
        try:
            c = canvas.Canvas(str(output_path), pagesize=A4)
            c.setTitle(title)
            
            width, height = A4
            margin = 20 * mm
            y_position = height - margin
            line_height = 5 * mm
            
            c.setFont("Helvetica", 12)
            
            for line in text.split("\n"):
                if y_position < margin:
                    c.showPage()
                    y_position = height - margin
                    c.setFont("Helvetica", 12)
                
                c.drawString(margin, y_position, line)
                y_position -= line_height
            
            c.save()
            return output_path
        except Exception as e:
            print(f"[PDF] Chyba při vytváření PDF: {e}")
            return None
    
    def list_pdfs(self) -> List[PDFInfo]:
        """
        Vrátí seznam PDF souborů v output adresáři.
        
        Returns:
            Seznam PDFInfo objektů
        """
        result = []
        for pdf_file in self.output_dir.glob("*.pdf"):
            info = self.get_pdf_info(pdf_file)
            if info:
                result.append(info)
        return result






