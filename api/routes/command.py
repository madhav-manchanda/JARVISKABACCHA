"""
api/routes/command.py — Core command processing endpoints.
Handles both text and voice commands, routing them through brain.py.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from auth import get_current_user
from brain import process
from api.models.command import TextCommandRequest, ConfirmRequest
from api.models.intent import JarvisResponse, Intent
from config import CONFIG
from voice import transcribe_bytes, speak, is_whisper_loaded
from utils.audio_utils import get_extension_from_content_type, is_allowed_audio
from actions.dork import execute_confirmed_dork
from actions.downloader import download

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Command"])


@router.post("/command/text", response_model=JarvisResponse)
async def command_text(
    req: TextCommandRequest,
    username: str = Depends(get_current_user),
) -> Any:
    """
    Process a natural language text command.
    Returns a structured intent JSON designed for Android execution.
    """
    intent_data = await process(req.text, req.session_id)
    
    follow_ups = []
    action = intent_data.get("action", "")
    params = intent_data.get("params", {})
    
    # ── Server-side pre-processing for complex tasks ──
    # If the AI chose google_search, execute it and convert results into open_url
    if action == "google_search":
        try:
            from actions.search import google_search
            query = params.get("query", "")
            num = params.get("num_results", 3)
            lang = intent_data.get("language", "en")
            search_result = await google_search(query, num, lang)
            if search_result.get("success") and search_result.get("sources"):
                sources = search_result["sources"]
                first_url = sources[0].get("url", "") if sources else ""
                if first_url:
                    follow_ups.append(Intent(
                        action="open_url",
                        app="browser",
                        params={"url": first_url},
                    ))
                # Update response text with the summary
                if search_result.get("summary"):
                    intent_data["response_text"] = search_result["summary"]
                intent_data["data"] = {"results": sources}
            elif not search_result.get("success"):
                # SerpAPI not configured — fallback to opening Google search directly on device
                import urllib.parse
                google_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}"
                follow_ups.append(Intent(
                    action="open_url",
                    app="browser",
                    params={"url": google_url},
                ))
                intent_data["execution_target"] = "device"
        except Exception as e:
            logger.warning("google_search pre-processing failed: %s", e)
            # Fallback: open Google search on device
            import urllib.parse
            query = params.get("query", "")
            if query:
                google_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}"
                follow_ups.append(Intent(
                    action="open_url",
                    app="browser",
                    params={"url": google_url},
                ))
                intent_data["execution_target"] = "device"
    
    # If the AI chose download_file, execute it server-side
    elif action == "download_file":
        try:
            url = params.get("url", "")
            if url:
                result = await download(url, req.session_id)
                intent_data["data"] = result
        except Exception as e:
            logger.warning("download_file pre-processing failed: %s", e)
    
    resp = JarvisResponse(
        success=True,
        session_id=req.session_id,
        language=intent_data.get("language", "en"),
        response_text=intent_data.get("response_text", ""),
        execution_target=intent_data.get("execution_target", "server"),
        intent=intent_data,
        follow_up_actions=follow_ups,
    )
    
    # Generate TTS if response text exists
    if resp.response_text:
        audio_path = speak(resp.response_text, resp.language)
        if audio_path:
            import os
            filename = os.path.basename(audio_path)
            resp.response_audio_url = f"/audio/{filename}"
            
    return resp


@router.post("/command/voice", response_model=JarvisResponse)
async def command_voice(
    audio: UploadFile = File(...),
    session_id: str = Form(None),
    username: str = Depends(get_current_user),
) -> Any:
    """
    Process a voice command.
    Transcribes audio via Whisper, then processes through brain.
    """
    if not is_whisper_loaded():
        raise HTTPException(status_code=503, detail="Whisper STT model not loaded")

    # Generate session ID if not provided
    if not session_id:
        import uuid
        session_id = uuid.uuid4().hex

    # Validate file size
    audio.file.seek(0, 2)
    size_mb = audio.file.tell() / (1024 * 1024)
    audio.file.seek(0)
    if size_mb > CONFIG.MAX_AUDIO_SIZE_MB:
        raise HTTPException(
            status_code=413, 
            detail=f"Audio file too large ({size_mb:.1f}MB > {CONFIG.MAX_AUDIO_SIZE_MB}MB)"
        )

    # Validate format
    ext = get_extension_from_content_type(audio.content_type) or ""
    if not ext and audio.filename:
        import os
        ext = os.path.splitext(audio.filename)[1].lower()
    
    if ext not in {".wav", ".mp3", ".m4a", ".ogg", ".webm", ".flac"}:
        # Accept it anyway and let ffmpeg try, but log warning
        logger.warning("Unusual audio format uploaded: %s (%s)", audio.content_type, ext)

    # Transcribe
    audio_bytes = await audio.read()
    stt_result = transcribe_bytes(audio_bytes, suffix=ext or ".wav")
    
    text = stt_result.get("text", "")
    if not text:
        return JarvisResponse(
            success=False,
            session_id=session_id,
            language="en",
            response_text="I couldn't hear anything. Please try again.",
            error="Silence detected or transcription failed",
            code="STT_FAILED"
        )

    # Process text through brain
    intent_data = await process(text, session_id, language_hint=stt_result.get("language"))
    
    resp = JarvisResponse(
        success=True,
        session_id=session_id,
        language=intent_data.get("language", "en"),
        transcribed_text=text,
        response_text=intent_data.get("response_text", ""),
        execution_target=intent_data.get("execution_target", "server"),
        intent=intent_data,
    )
    
    if resp.response_text:
        audio_path = speak(resp.response_text, resp.language)
        if audio_path:
            import os
            resp.response_audio_url = f"/audio/{os.path.basename(audio_path)}"
            
    return resp


@router.post("/command/confirm", response_model=JarvisResponse)
async def command_confirm(
    req: ConfirmRequest,
    username: str = Depends(get_current_user),
) -> Any:
    """
    Handle user confirmation for sensitive actions.
    If the action was server-side (like dork or dangerous download), it executes it here.
    If it was device-side (like upi_payment), this just logs it, and the Android app executes it locally.
    """
    if not req.confirmed:
        return JarvisResponse(
            success=True,
            session_id=req.session_id,
            response_text="Cancelled." if not req.dork_query else "Action cancelled.",
            execution_target="server"
        )
        
    # Handle Dork confirmation
    if req.dork_query:
        result = await execute_confirmed_dork(req.dork_query, session_id=req.session_id)
        return JarvisResponse(
            success=result["success"],
            session_id=req.session_id,
            response_text="Search executed." if result["success"] else "Search failed.",
            data=result,
            error=result.get("error")
        )
        
    # Handle dangerous download confirmation
    if req.download_url:
        result = await download(req.download_url, req.session_id)
        return JarvisResponse(
            success=result["success"],
            session_id=req.session_id,
            response_text=result.get("message", "Download started."),
            data=result
        )
        
    # For device actions (UPI, WhatsApp), the VPS just acknowledges.
    # Android app will see confirmed=True and proceed with AccessibilityService execution.
    return JarvisResponse(
        success=True,
        session_id=req.session_id,
        response_text="Confirmed. Executing now.",
        execution_target="device"
    )
