import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Set
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import Customer, SupportSession, SupportMessage as DBSupportMessage
from src.modules.vehicle_hub.routers_v1.auth import get_current_user
from src.core.security import decode_access_token_payload
from src.modules.email_client.service import EmailService, EmailMessage
from src.core.rbac import is_admin
from src.core.branding import APP_DISPLAY_NAME

router = APIRouter(prefix="/api/v1/support", tags=["support"])

SUPPORT_ADMIN_EMAIL = os.getenv("SUPPORT_NOTIFY_EMAIL", "podpora@toozservis.cz").strip() or "podpora@toozservis.cz"
SUPPORT_TIMEZONE = ZoneInfo("Europe/Prague")
SUPPORT_HOURS_LABEL = "Po–Pá 8:00–18:00"
_chat_online_notified_session_ids: Set[int] = set()


class OfflineContactRequest(BaseModel):
    subject: str = Field(..., min_length=3, max_length=180)
    message: str = Field(..., min_length=10, max_length=4000)
    contact_email: Optional[str] = Field(default=None, max_length=320)
    phone: Optional[str] = Field(default=None, max_length=40)


class ConnectionManager:
    def __init__(self):
        self.active_users: Dict[int, WebSocket] = {}
        self.active_admins: List[WebSocket] = []

    async def connect_user(self, websocket: WebSocket, customer_id: int, customer_email: Optional[str] = None):
        previous = self.active_users.get(customer_id)
        if previous is not None and previous is not websocket:
            try:
                await previous.close(code=1000)
            except Exception:
                pass
        await websocket.accept()
        self.active_users[customer_id] = websocket
        avail = compute_support_availability()
        await websocket.send_json({
            "type": "session_info",
            "customer_id": customer_id,
            "customer_email": customer_email,
            "business_hours": avail["in_business_hours"],
            "business_hours_label": SUPPORT_HOURS_LABEL,
            "admin_online": avail["admin_online"],
            "mode": avail["mode"],
            "status_label": avail["status_label"],
            "welcome": build_support_welcome_message(avail),
        })
        await websocket.send_json({
            "type": "admin_status",
            "online": avail["admin_online"],
        })

    def disconnect_user(self, customer_id: int):
        if customer_id in self.active_users:
            del self.active_users[customer_id]

    async def connect_admin(self, websocket: WebSocket):
        await websocket.accept()
        self.active_admins.append(websocket)
        await self.broadcast_admin_status(True)

    async def disconnect_admin(self, websocket: WebSocket):
        if websocket in self.active_admins:
            self.active_admins.remove(websocket)
        if len(self.active_admins) == 0:
            await self.broadcast_admin_status(False)

    async def broadcast_admin_status(self, online: bool):
        message = {"type": "admin_status", "online": online}
        avail = compute_support_availability()
        if online and avail["in_business_hours"]:
            status_label = "Operátor je online"
            mode = "live"
        elif avail["in_business_hours"]:
            status_label = "Čeká se na připojení operátora"
            mode = "waiting"
        else:
            status_label = "Mimo pracovní dobu — použijte kontaktní formulář"
            mode = "offline"
        message.update({
            "mode": mode,
            "status_label": status_label,
            "business_hours": avail["in_business_hours"],
        })
        for ws in self.active_users.values():
            try:
                await ws.send_json(message)
            except Exception:
                pass

    async def send_to_admin(self, message: dict):
        for ws in self.active_admins:
            try:
                await ws.send_json(message)
            except Exception:
                pass

    async def send_to_user(self, customer_id: int, message: dict):
        if customer_id in self.active_users:
            try:
                await self.active_users[customer_id].send_json(message)
            except Exception:
                pass


manager = ConnectionManager()


def compute_support_availability() -> dict:
    now = datetime.now(SUPPORT_TIMEZONE)
    in_hours = now.weekday() < 5 and 8 <= now.hour < 18
    admin_online = len(manager.active_admins) > 0
    if not in_hours:
        mode = "offline"
        status_label = "Mimo pracovní dobu — použijte kontaktní formulář"
    elif admin_online:
        mode = "live"
        status_label = "Operátor je online"
    else:
        mode = "waiting"
        status_label = "Čeká se na připojení operátora"
    return {
        "in_business_hours": in_hours,
        "admin_online": admin_online,
        "mode": mode,
        "status_label": status_label,
    }


def build_support_welcome_message(avail: Optional[dict] = None) -> str:
    avail = avail or compute_support_availability()
    if avail["mode"] == "offline":
        return (
            f"Dobrý den! Právě jsme mimo pracovní dobu ({SUPPORT_HOURS_LABEL}). "
            "Vyplňte prosím kontaktní formulář níže — odpověď pošleme na váš e-mail."
        )
    if avail["mode"] == "waiting":
        return (
            "Dobrý den! Jsem asistent podpory. Operátor se brzy připojí — "
            "mezitím nám můžete napsat zprávu."
        )
    return (
        "Dobrý den! Operátor podpory je online. "
        "Napište nám, rádi vám pomůžeme."
    )


def get_user_from_token(token: str, db: Session) -> Optional[Customer]:
    try:
        payload = decode_access_token_payload(token)
        email = (payload or {}).get("sub")
        if not email:
            return None
        from sqlalchemy import func
        customer = db.query(Customer).filter(func.lower(Customer.email) == str(email).strip().lower()).first()
        return customer
    except Exception:
        return None


def _get_or_create_active_session(db: Session, user: Customer) -> SupportSession:
    session = db.query(SupportSession).filter(
        SupportSession.customer_id == user.id,
        SupportSession.status == "active",
    ).first()
    if not session:
        session = SupportSession(customer_id=user.id, status="active")
        db.add(session)
        db.commit()
        db.refresh(session)
    return session


def _get_user_owned_session(db: Session, user_id: int, session_id: int) -> SupportSession:
    session = db.query(SupportSession).filter(
        SupportSession.id == session_id,
        SupportSession.customer_id == user_id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Požadavek nenalezen")
    return session


def _serialize_support_messages(messages: List[DBSupportMessage]) -> List[dict]:
    return [
        {
            "id": m.id,
            "sender_type": m.sender_type,
            "text": m.message,
            "created_at": m.created_at.isoformat(),
        } for m in messages
    ]


def _session_list_item(db: Session, session: SupportSession) -> dict:
    last_msg = db.query(DBSupportMessage).filter(
        DBSupportMessage.session_id == session.id
    ).order_by(DBSupportMessage.created_at.desc()).first()
    preview_source = (last_msg.message if last_msg else "") or ""
    if preview_source.startswith("[Offline formulář]"):
        preview = preview_source.replace("[Offline formulář]", "", 1).strip()
    else:
        preview = preview_source.strip()
    if len(preview) > 120:
        preview = preview[:117] + "…"
    return {
        "session_id": session.id,
        "status": session.status,
        "is_active": session.status == "active",
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
        "last_message": last_msg.message if last_msg else "",
        "last_message_time": (
            last_msg.created_at.isoformat() if last_msg and last_msg.created_at
            else (session.updated_at.isoformat() if session.updated_at else session.created_at.isoformat())
        ),
        "preview": preview or "Bez zpráv",
        "message_count": db.query(DBSupportMessage).filter(
            DBSupportMessage.session_id == session.id
        ).count(),
    }


def _send_support_admin_email(subject: str, body: str) -> bool:
    email_service = EmailService()
    if not email_service.is_configured():
        print("[SUPPORT] Email není nakonfigurován — upozornění neodesláno")
        return False
    try:
        return bool(email_service.send_simple_email(to=SUPPORT_ADMIN_EMAIL, subject=subject, body=body))
    except Exception as e:
        print(f"[SUPPORT] Chyba při odesílání emailu: {e}")
        return False


def _send_support_and_user_copy(
    *,
    support_subject: str,
    support_body: str,
    user_email: str,
    user_subject: str,
    user_body: str,
) -> bool:
    email_service = EmailService()
    if not email_service.is_configured():
        print("[SUPPORT] Email není nakonfigurován — e-maily neodeslány")
        return False
    ok = False
    try:
        ok = bool(email_service.send_simple_email(to=SUPPORT_ADMIN_EMAIL, subject=support_subject, body=support_body))
    except Exception as e:
        print(f"[SUPPORT] Chyba při odesílání e-mailu podpoře: {e}")
    if user_email:
        try:
            email_service.send_email(EmailMessage(
                to=[user_email.strip()],
                subject=user_subject,
                body=user_body,
            ))
        except Exception as e:
            print(f"[SUPPORT] Chyba při odesílání kopie uživateli: {e}")
    return ok


def notify_support_chat_user_online(user: Customer, session: SupportSession) -> None:
    global _chat_online_notified_session_ids
    session_id = int(session.id)
    if session_id in _chat_online_notified_session_ids:
        return
    _chat_online_notified_session_ids.add(session_id)

    user_name = (user.name or "").strip() or user.email
    avail = compute_support_availability()
    subject = f"[URGENT] Uživatel na online chatu – {user.email}"
    body = (
        "Dobrý den,\n\n"
        "Uživatel právě otevřel online chat podpory v aplikaci Správa vozidel.\n\n"
        f"ID uživatele: {user.id}\n"
        f"Jméno: {user_name}\n"
        f"E-mail: {user.email}\n"
        f"ID chat session: {session_id}\n"
        f"Pracovní doba: {'ano' if avail['in_business_hours'] else 'ne'}\n"
        f"Operátor v admin panelu: {'online' if avail['admin_online'] else 'offline'}\n\n"
        "Odpovězte v admin sekci Podpora (chat).\n\n"
        f"S pozdravem,\n{APP_DISPLAY_NAME}"
    )
    if _send_support_admin_email(subject, body):
        print(f"[SUPPORT] Upozornění na online chat odesláno na {SUPPORT_ADMIN_EMAIL} (session {session_id})")


def notify_support_chat_message(user: Customer, message: str, session_id: int, admins_online: bool) -> None:
    avail = compute_support_availability()
    if admins_online and avail["in_business_hours"]:
        return
    user_name = (user.name or "").strip() or user.email
    subject = f"[URGENT] Nová zpráva v online chatu – {user.email}"
    body = (
        "Dobrý den,\n\n"
        "Uživatel poslal zprávu přes online chat podpory.\n\n"
        f"ID uživatele: {user.id}\n"
        f"Jméno: {user_name}\n"
        f"E-mail: {user.email}\n"
        f"ID chat session: {session_id}\n"
        f"Operátor v admin panelu: {'online' if admins_online else 'offline'}\n\n"
        f"Zpráva:\n{message}\n\n"
        "Odpovězte v admin sekci Podpora (chat).\n\n"
        f"S pozdravem,\n{APP_DISPLAY_NAME}"
    )
    if _send_support_admin_email(subject, body):
        print(f"[SUPPORT] Upozornění na chat zprávu odesláno na {SUPPORT_ADMIN_EMAIL} (session {session_id})")


@router.get("/status")
def get_support_status(current_user: Customer = Depends(get_current_user)):
    avail = compute_support_availability()
    return {
        "business_hours": avail["in_business_hours"],
        "business_hours_label": SUPPORT_HOURS_LABEL,
        "admin_online": avail["admin_online"],
        "mode": avail["mode"],
        "status_label": avail["status_label"],
        "timezone": "Europe/Prague",
        "welcome": build_support_welcome_message(avail),
    }


@router.post("/offline-contact")
def submit_offline_contact(
    payload: OfflineContactRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    contact_email = (payload.contact_email or current_user.email or "").strip().lower()
    if not contact_email or "@" not in contact_email:
        raise HTTPException(status_code=400, detail="Zadejte platný kontaktní e-mail")

    subject = payload.subject.strip()
    message = payload.message.strip()
    phone = (payload.phone or current_user.phone or "").strip() or None
    user_name = (current_user.name or "").strip() or contact_email

    session = _get_or_create_active_session(db, current_user)
    db_msg = DBSupportMessage(
        session_id=session.id,
        sender_type="user",
        sender_id=current_user.id,
        message=f"[Offline formulář] {subject}: {message}",
    )
    db.add(db_msg)
    db.commit()

    created_at = datetime.now(SUPPORT_TIMEZONE).strftime("%d.%m.%Y %H:%M")
    support_subject = f"[Offline chat] {subject} – {contact_email}"
    support_body = (
        "Dobrý den,\n\n"
        "Uživatel odeslal kontaktní formulář mimo live chat (mimo pracovní dobu nebo offline režim).\n\n"
        f"Datum: {created_at}\n"
        f"Jméno: {user_name}\n"
        f"E-mail: {contact_email}\n"
        f"Telefon: {phone or '-'}\n"
        f"Předmět: {subject}\n\n"
        f"Zpráva:\n{message}\n\n"
        f"S pozdravem,\n{APP_DISPLAY_NAME}"
    )
    user_subject = f"Potvrzení: váš požadavek na podporu – {subject}"
    user_body = (
        f"Dobrý den,\n\n"
        "děkujeme za zprávu. Váš požadavek jsme přijali a tým podpory se vám ozve "
        f"v pracovní době ({SUPPORT_HOURS_LABEL}).\n\n"
        f"Předmět: {subject}\n\n"
        f"Vaše zpráva:\n{message}\n\n"
        f"S pozdravem,\nPodpora {APP_DISPLAY_NAME}\n{SUPPORT_ADMIN_EMAIL}"
    )

    if not _send_support_and_user_copy(
        support_subject=support_subject,
        support_body=support_body,
        user_email=contact_email,
        user_subject=user_subject,
        user_body=user_body,
    ):
        raise HTTPException(status_code=503, detail="E-mail se nepodařilo odeslat. Zkuste to později nebo napište přímo na podporu.")

    return {
        "message": "Požadavek byl odeslán. Kopii jsme poslali na váš e-mail.",
        "contact_email": contact_email,
    }


@router.websocket("/ws/user")
async def websocket_user(websocket: WebSocket, token: str = Query(...), db: Session = Depends(get_db)):
    user = get_user_from_token(token, db)
    if not user:
        await websocket.close(code=1008)
        return

    await manager.connect_user(websocket, user.id, user.email)
    session = _get_or_create_active_session(db, user)
    notify_support_chat_user_online(user, session)

    # Potvrzení identity relace klientovi (izolace per uživatel)
    await manager.send_to_user(user.id, {
        "type": "session_owner",
        "customer_id": user.id,
        "customer_email": user.email,
        "session_id": session.id,
    })

    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                msg_type = payload.get("type")

                if msg_type == "typing":
                    await manager.send_to_admin({
                        "type": "typing",
                        "customer_id": user.id,
                        "customer_email": user.email,
                        "sender_type": "user",
                        "active": bool(payload.get("active")),
                    })
                    continue

                if msg_type == "message":
                    session = _get_or_create_active_session(db, user)
                    avail = compute_support_availability()
                    if not avail["in_business_hours"]:
                        await manager.send_to_user(user.id, {
                            "type": "system",
                            "text": (
                                f"Mimo pracovní dobu ({SUPPORT_HOURS_LABEL}). "
                                "Použijte prosím kontaktní formulář v chatu."
                            ),
                        })
                        continue

                    text = payload.get("text", "").strip()
                    if not text:
                        continue

                    msg = DBSupportMessage(
                        session_id=session.id,
                        sender_type="user",
                        sender_id=user.id,
                        message=text,
                    )
                    db.add(msg)
                    db.commit()
                    db.refresh(msg)

                    msg_data = {
                        "type": "message",
                        "id": msg.id,
                        "session_id": session.id,
                        "sender_type": "user",
                        "sender_id": user.id,
                        "customer_id": user.id,
                        "customer_name": user.name or user.email,
                        "customer_email": user.email,
                        "text": text,
                        "created_at": msg.created_at.isoformat(),
                    }

                    await manager.send_to_user(user.id, msg_data)
                    admins_online = len(manager.active_admins) > 0
                    if admins_online:
                        await manager.send_to_admin(msg_data)
                    notify_support_chat_message(user, text, session.id, admins_online)
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect_user(user.id)


@router.websocket("/ws/admin")
async def websocket_admin(websocket: WebSocket, token: str = Query(...), db: Session = Depends(get_db)):
    user = get_user_from_token(token, db)
    if not user or not is_admin(user.role):
        await websocket.close(code=1008)
        return

    await manager.connect_admin(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                msg_type = payload.get("type")

                if msg_type == "typing":
                    customer_id = payload.get("customer_id")
                    if customer_id:
                        await manager.send_to_user(int(customer_id), {
                            "type": "typing",
                            "sender_type": "admin",
                            "active": bool(payload.get("active")),
                        })
                    continue

                if msg_type == "message":
                    text = payload.get("text", "").strip()
                    session_id = payload.get("session_id")
                    customer_id = payload.get("customer_id")

                    if text and session_id and customer_id:
                        msg = DBSupportMessage(
                            session_id=session_id,
                            sender_type="admin",
                            sender_id=user.id,
                            message=text,
                        )
                        db.add(msg)
                        db.commit()
                        db.refresh(msg)

                        msg_data = {
                            "type": "message",
                            "id": msg.id,
                            "session_id": session_id,
                            "sender_type": "admin",
                            "sender_id": user.id,
                            "customer_id": customer_id,
                            "text": text,
                            "created_at": msg.created_at.isoformat(),
                        }

                        await manager.send_to_user(int(customer_id), msg_data)
                        await manager.send_to_admin(msg_data)
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        await manager.disconnect_admin(websocket)


@router.get("/sessions")
def list_user_support_sessions(current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    sessions = db.query(SupportSession).filter(
        SupportSession.customer_id == current_user.id,
    ).order_by(SupportSession.updated_at.desc(), SupportSession.created_at.desc()).all()

    active_session = next((s for s in sessions if s.status == "active"), None)
    items = [_session_list_item(db, s) for s in sessions]
    previous = [item for item in items if not item["is_active"]]

    return {
        "customer_id": current_user.id,
        "customer_email": current_user.email,
        "active_session_id": active_session.id if active_session else None,
        "previous_count": len(previous),
        "sessions": items,
    }


@router.post("/sessions/new")
def start_new_support_session(current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    now = datetime.utcnow()
    active_sessions = db.query(SupportSession).filter(
        SupportSession.customer_id == current_user.id,
        SupportSession.status == "active",
    ).all()
    for session in active_sessions:
        session.status = "closed"
        session.updated_at = now

    new_session = SupportSession(customer_id=current_user.id, status="active", created_at=now, updated_at=now)
    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    return {
        "session_id": new_session.id,
        "customer_id": current_user.id,
        "customer_email": current_user.email,
        "status": new_session.status,
        "message": "Nový požadavek byl založen.",
    }


@router.get("/sessions/{session_id}/messages")
def get_user_session_messages(
    session_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = _get_user_owned_session(db, current_user.id, session_id)
    messages = db.query(DBSupportMessage).filter(
        DBSupportMessage.session_id == session.id
    ).order_by(DBSupportMessage.created_at.asc()).all()

    return {
        "customer_id": current_user.id,
        "customer_email": current_user.email,
        "session_id": session.id,
        "status": session.status,
        "is_active": session.status == "active",
        "read_only": session.status != "active",
        "messages": _serialize_support_messages(messages),
    }


@router.get("/history")
def get_user_history(current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    session = db.query(SupportSession).filter(
        SupportSession.customer_id == current_user.id,
        SupportSession.status == "active",
    ).first()

    if not session:
        return {
            "customer_id": current_user.id,
            "customer_email": current_user.email,
            "session_id": None,
            "status": None,
            "is_active": False,
            "read_only": False,
            "messages": [],
        }

    messages = db.query(DBSupportMessage).filter(
        DBSupportMessage.session_id == session.id
    ).order_by(DBSupportMessage.created_at.asc()).all()

    return {
        "customer_id": current_user.id,
        "customer_email": current_user.email,
        "session_id": session.id,
        "status": session.status,
        "is_active": True,
        "read_only": False,
        "messages": _serialize_support_messages(messages),
    }


@router.get("/admin/sessions")
def get_admin_sessions(current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    if not is_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Přístup odepřen")

    sessions = db.query(SupportSession).filter(SupportSession.status == "active").all()
    result = []
    for s in sessions:
        customer = db.query(Customer).filter(Customer.id == s.customer_id).first()
        last_msg = db.query(DBSupportMessage).filter(
            DBSupportMessage.session_id == s.id
        ).order_by(DBSupportMessage.created_at.desc()).first()

        result.append({
            "session_id": s.id,
            "customer_id": s.customer_id,
            "customer_name": customer.name if customer else "Neznámý",
            "customer_email": customer.email if customer else "Neznámý",
            "created_at": s.created_at.isoformat(),
            "last_message": last_msg.message if last_msg else "",
            "last_message_time": last_msg.created_at.isoformat() if last_msg else s.created_at.isoformat(),
            "is_online": s.customer_id in manager.active_users,
        })

    result.sort(key=lambda x: x["last_message_time"], reverse=True)
    return result


@router.get("/admin/sessions/{session_id}/messages")
def get_admin_session_messages(session_id: int, current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    if not is_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Přístup odpřen")

    messages = db.query(DBSupportMessage).filter(
        DBSupportMessage.session_id == session_id
    ).order_by(DBSupportMessage.created_at.asc()).all()
    return [
        {
            "id": m.id,
            "sender_type": m.sender_type,
            "text": m.message,
            "created_at": m.created_at.isoformat(),
        } for m in messages
    ]
