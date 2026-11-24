"""
Direct ElevenLabs TTS smoke test (bypasses Pipecat/WebRTC).

Run from the backend directory with .venv activated:
    python test_elevenlabs_tts.py

Reads ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID from backend/.env.
On success, saves test_elevenlabs_tts.mp3 in the current directory.
Does not print secrets.
"""

import os
import sys

import requests
from dotenv import find_dotenv, load_dotenv


def main() -> int:
    env_path = find_dotenv(usecwd=True)
    if env_path:
        load_dotenv(env_path, override=True)
        print(f".env file found: {env_path}")
    else:
        print("Could not find .env. Run this script from backend/.")
        return 1

    api_key = os.getenv("ELEVENLABS_API_KEY")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID")

    if not api_key or not voice_id:
        print("Missing ELEVENLABS_API_KEY or ELEVENLABS_VOICE_ID in .env.")
        return 1

    print("API key loaded:", bool(api_key))
    print("Voice ID loaded:", bool(voice_id))
    print("Testing direct ElevenLabs TTS with model eleven_flash_v2_5...")

    try:
        response = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            params={"output_format": "mp3_44100_128"},
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={
                "text": "Hello, this is a test of the clinic appointment assistant.",
                "model_id": "eleven_flash_v2_5",
            },
            timeout=60,
        )
    except requests.RequestException as exc:
        print("Request failed:", str(exc))
        return 2

    print("ElevenLabs response:", response.status_code)
    content_type = response.headers.get("Content-Type", "")
    print("Content-Type:", content_type)

    if response.status_code == 200 and response.content:
        output_path = "test_elevenlabs_tts.mp3"
        with open(output_path, "wb") as audio_file:
            audio_file.write(response.content)
        print(f"Success: audio generated ({len(response.content)} bytes).")
        print(f"Saved audio to: {os.path.abspath(output_path)}")
        return 0

    try:
        print("Error response:", response.json())
    except ValueError:
        print("Error response:", response.text[:1000])

    return 3


if __name__ == "__main__":
    sys.exit(main())
