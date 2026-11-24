"""
Verify that your ElevenLabs API key can access the configured voice.

Run from your backend directory:
    python verify_elevenlabs_voice.py

Reads ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID from backend/.env.
It never prints either secret value.
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
        load_dotenv(override=True)
        print("Warning: No .env file found from the current directory.")

    api_key = os.getenv("ELEVENLABS_API_KEY")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID")

    print("API key loaded:", bool(api_key))
    print("Voice ID loaded:", bool(voice_id))
    print("Voice ID length:", len(voice_id or ""))

    if not api_key or not voice_id:
        print("\nMissing configuration. Check ELEVENLABS_API_KEY and "
              "ELEVENLABS_VOICE_ID in backend/.env.")
        return 1

    try:
        response = requests.get(
            f"https://api.elevenlabs.io/v1/voices/{voice_id}",
            headers={"xi-api-key": api_key},
            timeout=20,
        )
    except requests.RequestException as exc:
        print("\nCould not reach ElevenLabs:", str(exc))
        return 2

    print("\nElevenLabs response:", response.status_code)

    if response.status_code == 200:
        print("Success: this API key can access the configured voice.")
        return 0

    try:
        body = response.json()
        detail = body.get("detail", body)
    except ValueError:
        detail = response.text[:500]

    print("Response:", detail)
    if response.status_code == 401:
        print("\nFor this lookup check, enable Voices → Read on the API key.")
    elif response.status_code == 404:
        print("\nCheck that ELEVENLABS_VOICE_ID is correct and available to your account.")

    return 3


if __name__ == "__main__":
    sys.exit(main())
