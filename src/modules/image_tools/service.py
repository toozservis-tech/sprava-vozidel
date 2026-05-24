"""
Image Tools Service - služba pro práci s obrázky
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple, List
from dataclasses import dataclass

# Pokusit se importovat Pillow
try:
    from PIL import Image, ImageFilter, ImageEnhance, ImageOps
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

from src.core.config import IMAGES_DIR


@dataclass
class ImageInfo:
    """Informace o obrázku"""
    path: Path
    width: int
    height: int
    format: str
    mode: str
    size_bytes: int


class ImageService:
    """Služba pro práci s obrázky"""
    
    def __init__(self):
        self.output_dir = IMAGES_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def is_available(self) -> bool:
        """Zkontroluje, zda je dostupná knihovna Pillow"""
        return PILLOW_AVAILABLE
    
    def get_image_info(self, image_path: Path) -> Optional[ImageInfo]:
        """
        Získá informace o obrázku.
        
        Args:
            image_path: Cesta k obrázku
            
        Returns:
            ImageInfo objekt nebo None
        """
        if not PILLOW_AVAILABLE:
            return None
        
        if not image_path.exists():
            return None
        
        try:
            with Image.open(image_path) as img:
                return ImageInfo(
                    path=image_path,
                    width=img.width,
                    height=img.height,
                    format=img.format or "unknown",
                    mode=img.mode,
                    size_bytes=image_path.stat().st_size
                )
        except Exception as e:
            print(f"[IMAGE] Chyba při čtení obrázku: {e}")
            return None
    
    def resize_image(
        self,
        image_path: Path,
        width: int,
        height: int,
        output_name: str,
        keep_aspect: bool = True
    ) -> Optional[Path]:
        """
        Změní velikost obrázku.
        
        Args:
            image_path: Cesta k obrázku
            width: Nová šířka
            height: Nová výška
            output_name: Název výstupního souboru
            keep_aspect: Zachovat poměr stran
            
        Returns:
            Cesta k výslednému obrázku nebo None
        """
        if not PILLOW_AVAILABLE:
            raise RuntimeError("Pillow není nainstalován")
        
        if not image_path.exists():
            return None
        
        output_path = self.output_dir / output_name
        
        try:
            with Image.open(image_path) as img:
                if keep_aspect:
                    img.thumbnail((width, height), Image.Resampling.LANCZOS)
                    result = img.copy()
                else:
                    result = img.resize((width, height), Image.Resampling.LANCZOS)
                
                # Zachovat formát nebo použít PNG
                fmt = img.format or "PNG"
                if fmt.upper() == "JPEG":
                    result = result.convert("RGB")
                
                result.save(output_path, format=fmt)
                return output_path
        except Exception as e:
            print(f"[IMAGE] Chyba při změně velikosti: {e}")
            return None
    
    def crop_image(
        self,
        image_path: Path,
        left: int,
        top: int,
        right: int,
        bottom: int,
        output_name: str
    ) -> Optional[Path]:
        """
        Ořízne obrázek.
        
        Args:
            image_path: Cesta k obrázku
            left, top, right, bottom: Souřadnice ořezu
            output_name: Název výstupního souboru
            
        Returns:
            Cesta k výslednému obrázku nebo None
        """
        if not PILLOW_AVAILABLE:
            raise RuntimeError("Pillow není nainstalován")
        
        if not image_path.exists():
            return None
        
        output_path = self.output_dir / output_name
        
        try:
            with Image.open(image_path) as img:
                cropped = img.crop((left, top, right, bottom))
                fmt = img.format or "PNG"
                if fmt.upper() == "JPEG":
                    cropped = cropped.convert("RGB")
                cropped.save(output_path, format=fmt)
                return output_path
        except Exception as e:
            print(f"[IMAGE] Chyba při ořezu: {e}")
            return None
    
    def rotate_image(
        self,
        image_path: Path,
        angle: int,
        output_name: str,
        expand: bool = True
    ) -> Optional[Path]:
        """
        Otočí obrázek.
        
        Args:
            image_path: Cesta k obrázku
            angle: Úhel otočení (ve stupních, proti směru hodinových ručiček)
            output_name: Název výstupního souboru
            expand: Rozšířit canvas pro celý otočený obrázek
            
        Returns:
            Cesta k výslednému obrázku nebo None
        """
        if not PILLOW_AVAILABLE:
            raise RuntimeError("Pillow není nainstalován")
        
        if not image_path.exists():
            return None
        
        output_path = self.output_dir / output_name
        
        try:
            with Image.open(image_path) as img:
                rotated = img.rotate(angle, expand=expand, resample=Image.Resampling.BICUBIC)
                fmt = img.format or "PNG"
                if fmt.upper() == "JPEG":
                    rotated = rotated.convert("RGB")
                rotated.save(output_path, format=fmt)
                return output_path
        except Exception as e:
            print(f"[IMAGE] Chyba při rotaci: {e}")
            return None
    
    def flip_image(
        self,
        image_path: Path,
        direction: str,
        output_name: str
    ) -> Optional[Path]:
        """
        Převrátí obrázek.
        
        Args:
            image_path: Cesta k obrázku
            direction: "horizontal" nebo "vertical"
            output_name: Název výstupního souboru
            
        Returns:
            Cesta k výslednému obrázku nebo None
        """
        if not PILLOW_AVAILABLE:
            raise RuntimeError("Pillow není nainstalován")
        
        if not image_path.exists():
            return None
        
        output_path = self.output_dir / output_name
        
        try:
            with Image.open(image_path) as img:
                if direction == "horizontal":
                    flipped = ImageOps.mirror(img)
                else:
                    flipped = ImageOps.flip(img)
                
                fmt = img.format or "PNG"
                if fmt.upper() == "JPEG":
                    flipped = flipped.convert("RGB")
                flipped.save(output_path, format=fmt)
                return output_path
        except Exception as e:
            print(f"[IMAGE] Chyba při převrácení: {e}")
            return None
    
    def apply_filter(
        self,
        image_path: Path,
        filter_name: str,
        output_name: str
    ) -> Optional[Path]:
        """
        Aplikuje filtr na obrázek.
        
        Args:
            image_path: Cesta k obrázku
            filter_name: Název filtru (blur, sharpen, contour, edge_enhance, grayscale)
            output_name: Název výstupního souboru
            
        Returns:
            Cesta k výslednému obrázku nebo None
        """
        if not PILLOW_AVAILABLE:
            raise RuntimeError("Pillow není nainstalován")
        
        if not image_path.exists():
            return None
        
        output_path = self.output_dir / output_name
        
        filters = {
            "blur": ImageFilter.BLUR,
            "sharpen": ImageFilter.SHARPEN,
            "contour": ImageFilter.CONTOUR,
            "edge_enhance": ImageFilter.EDGE_ENHANCE,
            "emboss": ImageFilter.EMBOSS,
            "smooth": ImageFilter.SMOOTH,
        }
        
        try:
            with Image.open(image_path) as img:
                if filter_name == "grayscale":
                    result = ImageOps.grayscale(img)
                elif filter_name in filters:
                    result = img.filter(filters[filter_name])
                else:
                    raise ValueError(f"Neznámý filtr: {filter_name}")
                
                fmt = img.format or "PNG"
                if fmt.upper() == "JPEG" and result.mode != "RGB":
                    result = result.convert("RGB")
                result.save(output_path, format=fmt)
                return output_path
        except Exception as e:
            print(f"[IMAGE] Chyba při aplikaci filtru: {e}")
            return None
    
    def adjust_brightness(
        self,
        image_path: Path,
        factor: float,
        output_name: str
    ) -> Optional[Path]:
        """
        Upraví jas obrázku.
        
        Args:
            image_path: Cesta k obrázku
            factor: Faktor jasu (1.0 = beze změny, < 1 tmavší, > 1 světlejší)
            output_name: Název výstupního souboru
            
        Returns:
            Cesta k výslednému obrázku nebo None
        """
        if not PILLOW_AVAILABLE:
            raise RuntimeError("Pillow není nainstalován")
        
        if not image_path.exists():
            return None
        
        output_path = self.output_dir / output_name
        
        try:
            with Image.open(image_path) as img:
                enhancer = ImageEnhance.Brightness(img)
                result = enhancer.enhance(factor)
                
                fmt = img.format or "PNG"
                if fmt.upper() == "JPEG":
                    result = result.convert("RGB")
                result.save(output_path, format=fmt)
                return output_path
        except Exception as e:
            print(f"[IMAGE] Chyba při úpravě jasu: {e}")
            return None
    
    def convert_format(
        self,
        image_path: Path,
        output_format: str,
        output_name: str
    ) -> Optional[Path]:
        """
        Převede obrázek do jiného formátu.
        
        Args:
            image_path: Cesta k obrázku
            output_format: Cílový formát (PNG, JPEG, BMP, GIF)
            output_name: Název výstupního souboru
            
        Returns:
            Cesta k výslednému obrázku nebo None
        """
        if not PILLOW_AVAILABLE:
            raise RuntimeError("Pillow není nainstalován")
        
        if not image_path.exists():
            return None
        
        output_path = self.output_dir / output_name
        
        try:
            with Image.open(image_path) as img:
                if output_format.upper() in ["JPEG", "JPG"]:
                    img = img.convert("RGB")
                
                img.save(output_path, format=output_format.upper())
                return output_path
        except Exception as e:
            print(f"[IMAGE] Chyba při konverzi formátu: {e}")
            return None
    
    def list_images(self) -> List[ImageInfo]:
        """
        Vrátí seznam obrázků v output adresáři.
        
        Returns:
            Seznam ImageInfo objektů
        """
        result = []
        extensions = [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"]
        
        for ext in extensions:
            for image_file in self.output_dir.glob(f"*{ext}"):
                info = self.get_image_info(image_file)
                if info:
                    result.append(info)
        
        return result






