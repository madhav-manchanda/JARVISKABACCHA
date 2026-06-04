"""
api/routes/memory.py — Endpoints to manage conversation history and facts.
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Any

from auth import get_current_user
from memory import get_history, save_fact, get_fact, list_facts, delete_fact
from api.models.auth import FactCreate

router = APIRouter(tags=["Memory"])


@router.get("/memory/history")
async def read_history(
    session_id: str,
    limit: int = 20,
    username: str = Depends(get_current_user),
) -> Any:
    """Get conversation history for a specific session."""
    history = await get_history(session_id, limit)
    return {"success": True, "history": history}


@router.get("/memory/facts")
async def read_facts(username: str = Depends(get_current_user)) -> Any:
    """List all saved facts."""
    facts = await list_facts()
    return {"success": True, "facts": facts}


@router.post("/memory/facts")
async def create_fact(
    fact: FactCreate,
    username: str = Depends(get_current_user),
) -> Any:
    """Save or update a key-value fact."""
    await save_fact(fact.key, fact.value)
    return {"success": True, "message": f"Fact '{fact.key}' saved successfully"}


@router.get("/memory/facts/{key}")
async def read_fact(key: str, username: str = Depends(get_current_user)) -> Any:
    """Get a specific fact by key."""
    fact = await get_fact(key)
    if not fact:
        raise HTTPException(status_code=404, detail="Fact not found")
    return {"success": True, "fact": fact}


@router.delete("/memory/facts/{key}")
async def remove_fact(key: str, username: str = Depends(get_current_user)) -> Any:
    """Delete a specific fact."""
    deleted = await delete_fact(key)
    if not deleted:
        raise HTTPException(status_code=404, detail="Fact not found")
    return {"success": True, "message": f"Fact '{key}' deleted"}
