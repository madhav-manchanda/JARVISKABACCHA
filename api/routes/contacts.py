"""
api/routes/contacts.py — CRUD endpoints for managing address book contacts.
Used to resolve names for WhatsApp, Calls, and UPI.
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Any

from auth import get_current_user
from memory import (
    list_contacts, save_contact, get_contact,
    update_contact, delete_contact, search_contacts
)
from api.models.auth import ContactCreate, ContactUpdate

router = APIRouter(tags=["Contacts"])


@router.get("/contacts")
async def read_contacts(
    query: str = None,
    username: str = Depends(get_current_user)
) -> Any:
    """List all contacts, or search by name."""
    if query:
        contacts = await search_contacts(query)
    else:
        contacts = await list_contacts()
    return {"success": True, "contacts": contacts}


@router.post("/contacts")
async def create_new_contact(
    contact: ContactCreate,
    username: str = Depends(get_current_user)
) -> Any:
    """Add a new contact."""
    contact_id = await save_contact(
        contact.name,
        contact.phone,
        contact.whatsapp,
        contact.upi_id
    )
    return {"success": True, "id": contact_id}


@router.get("/contacts/{contact_id}")
async def read_single_contact(
    contact_id: int,
    username: str = Depends(get_current_user)
) -> Any:
    """Get a contact by ID."""
    contact = await get_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return {"success": True, "contact": contact}


@router.put("/contacts/{contact_id}")
async def update_existing_contact(
    contact_id: int,
    contact: ContactUpdate,
    username: str = Depends(get_current_user)
) -> Any:
    """Update an existing contact."""
    updated = await update_contact(
        contact_id,
        contact.name,
        contact.phone,
        contact.whatsapp,
        contact.upi_id
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Contact not found or no changes provided")
    return {"success": True}


@router.delete("/contacts/{contact_id}")
async def remove_contact(
    contact_id: int,
    username: str = Depends(get_current_user)
) -> Any:
    """Delete a contact."""
    deleted = await delete_contact(contact_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Contact not found")
    return {"success": True}
