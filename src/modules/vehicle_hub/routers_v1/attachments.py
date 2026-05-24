"""
Attachments API v1.0 router
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Attachment, Customer
from .auth import get_current_user
from .schemas import AttachmentCreateV1, AttachmentOutV1, AttachmentUpdateV1

router = APIRouter(prefix="/attachments", tags=["attachments-v1"])


@router.get("", response_model=List[AttachmentOutV1])
def get_attachments(
    entity_type: str = None,
    entity_id: int = None,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Získá seznam všech příloh aktuálního uživatele"""
    try:
        query = db.query(Attachment).filter(
            Attachment.tenant_id == current_user.tenant_id,
            Attachment.user_id == current_user.id,
        )

        if entity_type:
            query = query.filter(Attachment.entity_type == entity_type)
        if entity_id:
            query = query.filter(Attachment.entity_id == entity_id)

        attachments = query.all()
        return attachments
    except Exception as e:
        print(f"[ATTACHMENTS] Error getting attachments: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Chyba při načítání příloh: {str(e)}"
        )


@router.get("/{attachment_id}", response_model=AttachmentOutV1)
def get_attachment(
    attachment_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Získá detail přílohy"""
    try:
        attachment = (
            db.query(Attachment)
            .filter(
                Attachment.id == attachment_id,
                Attachment.tenant_id == current_user.tenant_id,
                Attachment.user_id == current_user.id,
            )
            .first()
        )

        if not attachment:
            raise HTTPException(status_code=404, detail="Příloha nenalezena")

        return attachment
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ATTACHMENTS] Error getting attachment {attachment_id}: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Chyba při načítání přílohy: {str(e)}"
        )


@router.post("", response_model=AttachmentOutV1, status_code=201)
def create_attachment(
    attachment_data: AttachmentCreateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Vytvoří novou přílohu"""
    try:
        attachment = Attachment(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            file_name=attachment_data.file_name,
            file_type=attachment_data.file_type,
            file_size=attachment_data.file_size,
            file_path=attachment_data.file_path,
            description=attachment_data.description,
            entity_type=attachment_data.entity_type,
            entity_id=attachment_data.entity_id,
        )

        db.add(attachment)
        db.commit()
        db.refresh(attachment)

        return attachment
    except Exception as e:
        db.rollback()
        print(f"[ATTACHMENTS] Error creating attachment: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Chyba při vytváření přílohy: {str(e)}"
        )


@router.put("/{attachment_id}", response_model=AttachmentOutV1)
def update_attachment(
    attachment_id: int,
    attachment_data: AttachmentUpdateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Aktualizuje přílohu"""
    try:
        attachment = (
            db.query(Attachment)
            .filter(
                Attachment.id == attachment_id,
                Attachment.tenant_id == current_user.tenant_id,
                Attachment.user_id == current_user.id,
            )
            .first()
        )

        if not attachment:
            raise HTTPException(status_code=404, detail="Příloha nenalezena")

        # Aktualizovat pouze poskytnutá pole
        if attachment_data.file_name is not None:
            attachment.file_name = attachment_data.file_name
        if attachment_data.file_type is not None:
            attachment.file_type = attachment_data.file_type
        if attachment_data.file_size is not None:
            attachment.file_size = attachment_data.file_size
        if attachment_data.file_path is not None:
            attachment.file_path = attachment_data.file_path
        if attachment_data.description is not None:
            attachment.description = attachment_data.description
        if attachment_data.entity_type is not None:
            attachment.entity_type = attachment_data.entity_type
        if attachment_data.entity_id is not None:
            attachment.entity_id = attachment_data.entity_id

        db.commit()
        db.refresh(attachment)

        return attachment
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"[ATTACHMENTS] Error updating attachment {attachment_id}: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Chyba při aktualizaci přílohy: {str(e)}"
        )


@router.delete("/{attachment_id}", status_code=204)
def delete_attachment(
    attachment_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Smaže přílohu"""
    try:
        attachment = (
            db.query(Attachment)
            .filter(
                Attachment.id == attachment_id,
                Attachment.tenant_id == current_user.tenant_id,
                Attachment.user_id == current_user.id,
            )
            .first()
        )

        if not attachment:
            raise HTTPException(status_code=404, detail="Příloha nenalezena")

        db.delete(attachment)
        db.commit()

        return None
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"[ATTACHMENTS] Error deleting attachment {attachment_id}: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Chyba při mazání přílohy: {str(e)}"
        )
