"""Shared vehicle document platform (C1.0)."""

from .document_registry import DOCUMENT_REGISTRY, DocumentTypeDef, get_document_type
from .document_renderer import render_platform_document_pdf
from .document_service import (
    create_platform_document,
    get_document_for_user,
    list_documents_for_vehicle,
    serialize_document_card,
)
from .document_schemas import (
    DOCUMENT_STATUSES,
    DOCUMENT_TYPES,
    VISIBILITY_SCOPES,
    PlatformDocumentPayload,
)

__all__ = [
    "DOCUMENT_REGISTRY",
    "DOCUMENT_STATUSES",
    "DOCUMENT_TYPES",
    "VISIBILITY_SCOPES",
    "DocumentTypeDef",
    "PlatformDocumentPayload",
    "create_platform_document",
    "get_document_for_user",
    "get_document_type",
    "list_documents_for_vehicle",
    "render_platform_document_pdf",
    "serialize_document_card",
]
