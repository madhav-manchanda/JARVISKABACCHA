"""
api/routes/downloads.py — Download monitoring and status endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Any

from auth import get_current_user
from memory import list_downloads, get_download
from utils.file_utils import list_files_in_dir
from config import CONFIG

router = APIRouter(tags=["Downloads"])


@router.get("/downloads/status")
async def read_downloads(username: str = Depends(get_current_user)) -> Any:
    """List all download records with their status and progress."""
    downloads = await list_downloads()
    return {"success": True, "downloads": downloads}


@router.get("/downloads/{download_id}/progress")
async def read_download_progress(
    download_id: int,
    username: str = Depends(get_current_user)
) -> Any:
    """Get the current progress of a specific download."""
    from actions.downloader import get_progress
    res = await get_progress(download_id)
    if not res.get("success"):
        raise HTTPException(status_code=404, detail=res.get("error"))
    return res


@router.get("/downloads/files")
async def read_downloaded_files(
    session_id: str = None,
    username: str = Depends(get_current_user)
) -> Any:
    """
    List actual downloaded files on disk.
    If session_id is provided, lists files in that session's folder.
    Otherwise, lists files in the root downloads folder.
    """
    import os
    target_dir = CONFIG.DOWNLOAD_FOLDER
    if session_id:
        from utils.file_utils import ensure_session_dir
        target_dir = str(ensure_session_dir(CONFIG.DOWNLOAD_FOLDER, session_id))
    
    files = list_files_in_dir(target_dir)
    return {"success": True, "files": files, "directory": os.path.basename(target_dir)}
