import logging
import asyncio
from typing import Optional, Dict, Any
from shazamio import Shazam

logger = logging.getLogger(__name__)

async def recognize_song(audio_bytes: bytes) -> Optional[Dict[str, Any]]:
    """
    Takes raw audio bytes, feeds them to Shazamio, and returns a dictionary
    containing the recognized song info (title, artist, spotify_url, youtube_url) 
    or None if no match is found.
    """
    try:
        shazam = Shazam()
        # Shazamio can process raw bytes directly
        out = await shazam.recognize(audio_bytes)
        
        if not out.get('track'):
            logger.info("Shazam returned no track match.")
            return None
            
        track = out['track']
        title = track.get('title', 'Unknown Title')
        subtitle = track.get('subtitle', 'Unknown Artist')
        
        # Try to extract links if available
        spotify_url = None
        youtube_url = None
        
        # Shazamio usually returns a 'hub' with providers
        hub = track.get('hub', {})
        providers = hub.get('providers', [])
        for provider in providers:
            if provider.get('type') == 'SPOTIFY':
                spotify_url = provider.get('actions', [{}])[0].get('uri')
            
        return {
            "title": title,
            "artist": subtitle,
            "spotify_url": spotify_url,
            "youtube_url": youtube_url
        }
    except Exception as e:
        logger.error(f"Error during Shazam recognition: {e}")
        return None
