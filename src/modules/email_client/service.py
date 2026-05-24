"""
Email Client Service - služba pro odesílání emailů
"""
from __future__ import annotations

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.utils import make_msgid, formatdate
from typing import Optional, List, Tuple
from pathlib import Path
from dataclasses import dataclass, field

from src.core.branding import APP_DISPLAY_NAME
from src.core.config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM
from src.modules.email_client.templates import build_app_url, render_email_layout, render_panel


@dataclass
class EmailMessage:
    """Reprezentace emailové zprávy"""
    to: List[str]
    subject: str
    body: str
    html_body: Optional[str] = None
    reply_to: Optional[List[str]] = None
    cc: Optional[List[str]] = None
    bcc: Optional[List[str]] = None
    attachments: Optional[List[Path]] = None
    # (filename, bytes, mime) — např. ("vypis.pdf", data, "application/pdf")
    attachment_blobs: List[Tuple[str, bytes, str]] = field(default_factory=list)


class EmailService:
    """Služba pro odesílání emailů"""
    
    def __init__(
        self,
        host: str = SMTP_HOST,
        port: int = SMTP_PORT,
        username: str = SMTP_USER,
        password: str = SMTP_PASSWORD,
        from_email: str = SMTP_FROM
    ):
        self.host = host
        self.port = port
        self.username = username.strip() if username else None
        # Vyčistit heslo - odstranit jen bílé znaky a uvozovky (středník je součástí hesla)
        if password:
            self.password = password.strip().strip('"').strip("'")
        else:
            self.password = None
        self.from_email = from_email
    
    def is_configured(self) -> bool:
        """Zkontroluje, zda je email správně nakonfigurován"""
        return bool(self.username and self.password and self.host)
    
    def send_email(self, message: EmailMessage) -> bool:
        """
        Odešle email.
        
        Args:
            message: EmailMessage objekt s daty emailu
            
        Returns:
            True pokud email byl úspěšně odeslán
            
        Raises:
            ValueError: Pokud nejsou nakonfigurovány SMTP údaje
            smtplib.SMTPException: Při chybě odesílání
        """
        if not self.is_configured():
            raise ValueError("Email není nakonfigurován. Nastavte SMTP údaje v konfiguraci.")
        
        # Vytvořit zprávu
        msg = MIMEMultipart("alternative")
        msg["From"] = self.from_email
        msg["To"] = ", ".join(message.to)
        msg["Subject"] = message.subject
        msg["Message-ID"] = make_msgid(domain="toozservis.cz")
        msg["Date"] = formatdate(localtime=True)
        if message.reply_to:
            msg["Reply-To"] = ", ".join(message.reply_to)
        
        if message.cc:
            msg["Cc"] = ", ".join(message.cc)
        
        # Přidat text body
        msg.attach(MIMEText(message.body, "plain", "utf-8"))
        
        # Přidat HTML body (pokud existuje)
        if message.html_body:
            msg.attach(MIMEText(message.html_body, "html", "utf-8"))
        
        # Přidat přílohy
        if message.attachments:
            for attachment_path in message.attachments:
                self._add_attachment(msg, attachment_path)
        if message.attachment_blobs:
            for filename, blob, mime in message.attachment_blobs:
                self._add_attachment_bytes(msg, blob, filename, mime)
        
        # Seznam všech příjemců
        all_recipients = list(message.to)
        if message.cc:
            all_recipients.extend(message.cc)
        if message.bcc:
            all_recipients.extend(message.bcc)
        
        # Odeslat email
        try:
            # Port 465 vyžaduje SSL (SMTP_SSL), port 587 vyžaduje STARTTLS
            tls_context = ssl.create_default_context()
            if self.port == 465:
                # SSL připojení pro port 465 (např. Webnode)
                print(f"[EMAIL] Connecting to {self.host}:{self.port} using SMTP_SSL")
                with smtplib.SMTP_SSL(
                    self.host, self.port, timeout=30, context=tls_context
                ) as server:
                    print(f"[EMAIL] Connected, authenticating as {self.username}")
                    server.login(self.username, self.password)
                    print(f"[EMAIL] Authenticated, sending email to {len(all_recipients)} recipient(s)")
                    server.sendmail(self.from_email, all_recipients, msg.as_string())
                    print(f"[EMAIL] Email successfully sent")
            else:
                # STARTTLS (587) — po starttls znovu EHLO (RFC), jinak některé servery ukončí spojení při AUTH
                print(f"[EMAIL] Connecting to {self.host}:{self.port} using SMTP + STARTTLS")
                with smtplib.SMTP(self.host, self.port, timeout=30) as server:
                    server.ehlo()
                    print(f"[EMAIL] Connected, starting TLS")
                    server.starttls(context=tls_context)
                    server.ehlo()
                    print(f"[EMAIL] TLS started, authenticating as {self.username}")
                    server.login(self.username, self.password)
                    print(f"[EMAIL] Authenticated, sending email to {len(all_recipients)} recipient(s)")
                    server.sendmail(self.from_email, all_recipients, msg.as_string())
                    print(f"[EMAIL] Email successfully sent")
            return True
        except smtplib.SMTPAuthenticationError as e:
            print(f"[EMAIL] Authentication failed: {e}")
            raise ValueError("SMTP autentizace selhala - zkontrolujte uživatelské jméno a heslo")
        except smtplib.SMTPConnectError as e:
            print(f"[EMAIL] Connection failed: {e}")
            raise ValueError(f"Nelze se připojit k SMTP serveru {self.host}:{self.port}")
        except smtplib.SMTPException as e:
            print(f"[EMAIL] SMTP error: {e}")
            raise
        except Exception as e:
            print(f"[EMAIL] Unexpected error: {type(e).__name__}: {e}")
            raise
    
    def _add_attachment(self, msg: MIMEMultipart, file_path: Path) -> None:
        """Přidá přílohu k emailu"""
        if not file_path.exists():
            print(f"[EMAIL] Příloha neexistuje: {file_path}")
            return
        
        with open(file_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f"attachment; filename={file_path.name}"
        )
        msg.attach(part)

    def _add_attachment_bytes(self, msg: MIMEMultipart, data: bytes, filename: str, mime: str) -> None:
        if not data:
            print(f"[EMAIL] Příloha {filename} je prázdná, přeskočeno")
            return
        parts = mime.split("/", 1)
        maintype = parts[0] if parts else "application"
        subtype = parts[1] if len(parts) > 1 else "octet-stream"
        part = MIMEBase(maintype, subtype)
        part.set_payload(data)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={filename}")
        msg.attach(part)
    
    def send_simple_email(
        self,
        to: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None
    ) -> bool:
        """
        Zjednodušené odeslání emailu.
        
        Args:
            to: Email příjemce
            subject: Předmět emailu
            body: Text emailu
            html_body: HTML verze emailu (volitelné)
            
        Returns:
            True pokud byl email úspěšně odeslán
        """
        message = EmailMessage(
            to=[to],
            subject=subject,
            body=body,
            html_body=html_body
        )
        return self.send_email(message)
    
    def send_vehicle_reminder(
        self,
        to: str,
        vehicle_name: str,
        reminder_type: str,
        due_date: str
    ) -> bool:
        """
        Odešle připomínku ohledně vozidla (STK, pojištění, servis atd.)
        
        Args:
            to: Email příjemce
            vehicle_name: Název vozidla
            reminder_type: Typ připomínky (STK, pojištění, servis)
            due_date: Datum expirace
            
        Returns:
            True pokud byl email úspěšně odeslán
        """
        subject = f"Připomínka: {reminder_type} - {vehicle_name}"
        
        body = f"""Dobrý den,

připomínáme Vám blížící se termín pro Vaše vozidlo {vehicle_name}:

Typ: {reminder_type}
Datum: {due_date}

S pozdravem,
{APP_DISPLAY_NAME}
"""
        
        html_body = render_email_layout(
            title="Připomínka k vozidlu",
            subtitle="Blíží se důležitý termín.",
            intro="Dobrý den,",
            paragraphs=[
                "připomínáme Vám blížící se termín pro Vaše vozidlo.",
                "Nezapomeňte si včas zajistit potřebné úkony.",
            ],
            panels=[
                render_panel(
                    title="Přehled připomínky",
                    rows=[
                        ("Vozidlo", vehicle_name),
                        ("Typ", reminder_type),
                        ("Datum", due_date),
                    ],
                )
            ],
            cta_label="Otevřít aplikaci",
            cta_url=build_app_url(),
            accent="#f59e0b",
        )
        
        return self.send_simple_email(to, subject, body, html_body)
