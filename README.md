# Jarvis VPS Core

A headless AI assistant brain designed to run on a Linux VPS. It uses Claude 3.5 Sonnet for intelligence and OpenAI Whisper for speech-to-text.

**Architecture Note:** This VPS serves as the "brain". It executes server-side actions (like searching, dorking, and downloading) directly. For device-side actions (like making calls, sending WhatsApp messages, or setting alarms), it returns a structured JSON intent meant to be executed by a companion Android app (to be built separately).

## Features
- **Voice & Text Commands:** Accepts natural language input in Hindi, English, Hinglish, and more.
- **Server Actions:** Google Search (via SerpAPI), Google Dorking (always requires confirmation), File/Video Downloads (via yt-dlp), Weather, System Info.
- **Device Intents:** Formats exact intents for WhatsApp, Calls, SMS, UPI Payments, Alarms, and App launching.
- **Memory:** SQLite (with WAL) for facts, contacts, and intent logging. Redis for fast conversation history caching.
- **Security:** JWT authentication, rate limiting, and dangerous download warnings.

## Deployment Instructions

### 1. Requirements
- Docker and docker-compose
- A domain name (optional, but recommended for HTTPS)

### 2. Setup
1. Clone the repository on your VPS.
2. Create your `.env` file:
   ```bash
   cp .env.example .env
   nano .env
   ```
3. Fill in the required keys (`ANTHROPIC_API_KEY`, `JWT_SECRET`, `JARVIS_PASSWORD`).

### 3. Run with Docker
```bash
docker-compose up -d --build
```
This will start the FastAPI backend, Redis, and Nginx reverse proxy. 

To view logs:
```bash
docker-compose logs -f jarvis
```

### 4. HTTPS (Production)
For a production deployment, you should secure the API with SSL:
```bash
# Assuming you have certbot installed on the host
certbot --nginx -d yourdomain.com
```

---

## API & Android Integration Guide

This API uses a strict intent contract designed so the companion Android app requires zero backend changes to add device features.

### Authentication
1. `POST /auth/login` with `{"username": "...", "password": "..."}`
2. Receive `access_token` and `refresh_token`.
3. Include header `Authorization: Bearer <access_token>` on all requests.

### Core Command Endpoints

**1. Text Command**
`POST /command/text`
```json
{
  "text": "Rahul ko 500 rupay bhejo GPay se",
  "session_id": "optional_session_id"
}
```

**2. Voice Command**
`POST /command/voice` (multipart/form-data)
- `audio`: File upload (WAV/MP3/M4A/OGG)
- `session_id`: (optional string)

### The Intent Contract Response
Every command returns this shape:
```json
{
  "success": true,
  "session_id": "abc123",
  "language": "hi",
  "transcribed_text": "Rahul ko 500 rupay bhejo",
  "response_text": "Rahul ko GPay se ₹500 bhej raha hun",
  "response_audio_url": "/audio/tts_xyz.wav",
  "execution_target": "device",
  "intent": {
    "action": "upi_payment",
    "app": "gpay",
    "params": {
      "contact": "Rahul",
      "amount": 500
    },
    "confirmation_required": true,
    "confirmation_message": "GPay se Rahul ko ₹500 bhejna hai. Confirm karein?"
  }
}
```

### Execution Target Logic
Your Android app should check `execution_target`:
- If `"server"`: The VPS has already performed the action (e.g. downloaded a file). The app should just speak the `response_text` or play the `response_audio_url`.
- If `"device"`: The app needs to read `intent.action` and `intent.params` and execute the action locally using AccessibilityService or Android Intents.

### Confirmations
If `intent.confirmation_required` is `true`:
1. Ask the user the `confirmation_message`.
2. Send the user's answer to `POST /command/confirm`:
   ```json
   {
     "session_id": "abc123",
     "confirmed": true,
     "intent_id": "..."
   }
   ```
3. Proceed with the device action.

### Real-Time WebSockets
Connect to `/ws/{session_id}?token=<jwt>` to receive real-time push events for background downloads and server action completions.

## Usage Examples (Postman / cURL)

**Get System Info:**
"Server kaisa chal raha hai?" -> `system_info` (Server executes, returns stats)

**Google Search:**
"Who won the 2024 IPL?" -> `google_search` (Server searches, returns summary)

**Download YouTube Video:**
"Download this video: https://youtube.com/..." -> `download_video` (Server starts yt-dlp in background, WS pushes progress)

**UPI Payment (Device intent):**
"Pay 150 to electricity bill via PhonePe" -> returns `upi_payment` intent.

---
*Built for Madhav.*
