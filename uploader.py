# One-time setup (YouTube Data API v3 + OAuth):
# 1. Google Cloud Console → APIs → enable "YouTube Data API v3".
# 2. Credentials → Create OAuth client ID → Desktop app (NOT Web) → download JSON.
# 3. Save the file as credentials.json in this folder (must contain "installed" key).
# 4. Run:  python uploader.py --authenticate
#    Uses installed-app loopback (random localhost port). No redirect URIs to add in Console.
# 5. token.json is created. For GitHub Actions, add secrets:
#      GOOGLE_CREDENTIALS = base64 of credentials.json
#      GOOGLE_TOKEN       = base64 of token.json
#    macOS: base64 -i credentials.json | pbcopy
#           base64 -i token.json | pbcopy
# 6. Daily runs: python main.py && python uploader.py

import argparse
import base64
import json
import os
import pickle
import sys
from pathlib import Path

WORK_DIR = Path(__file__).resolve().parent
SHORT_PATH = WORK_DIR / "shorts.mp4"
LEGACY_SHORT_PATH = WORK_DIR / "short.mp4"
TITLE_PATH = WORK_DIR / "title.txt"
CREDENTIALS_PATH = WORK_DIR / "credentials.json"
TOKEN_JSON_PATH = WORK_DIR / "token.json"
TOKEN_PICKLE_PATH = WORK_DIR / "token.pickle"
VOICE_PATH = WORK_DIR / "voice.mp3"
CLIPS_DIR = WORK_DIR / "clips"

DESCRIPTION = "Follow for daily facts!\n#shorts #facts #viral"
SHORTS_TAGS = ["shorts", "facts", "viral", "youtubeshorts"]
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def log(step: str, message: str) -> None:
    print(f"[{step}] {message}", flush=True)


def decode_secret_to_file(env_name: str, dest: Path, label: str) -> bool:
    raw = os.environ.get(env_name)
    if not raw:
        return False
    try:
        dest.write_bytes(base64.b64decode(raw.strip()))
        log("auth", f"Wrote {label} from {env_name} → {dest.name}")
        return True
    except Exception as exc:
        raise RuntimeError(f"Failed to decode {env_name}: {exc}") from exc


def load_installed_credentials() -> None:
    """Ensure credentials.json exists and is a Desktop (installed) OAuth client."""
    with open(CREDENTIALS_PATH, encoding="utf-8") as cred_file:
        data = json.load(cred_file)
    if data.get("web") and not data.get("installed"):
        raise RuntimeError(
            "credentials.json is a Web OAuth client. Create a Desktop application "
            "OAuth client in Google Cloud Console and download the new JSON."
        )
    if not data.get("installed"):
        raise RuntimeError(
            "credentials.json must contain an 'installed' block (Desktop OAuth client)."
        )
    log("auth", "Using Google OAuth Desktop (installed application) client.")


def ensure_credentials_file() -> None:
    log("auth", "Loading OAuth client credentials...")
    if CREDENTIALS_PATH.exists():
        log("auth", f"Using {CREDENTIALS_PATH}")
        load_installed_credentials()
        return
    if decode_secret_to_file("GOOGLE_CREDENTIALS", CREDENTIALS_PATH, "credentials.json"):
        load_installed_credentials()
        return
    if decode_secret_to_file("GOOGLE_CREDENTIALS_JSON", CREDENTIALS_PATH, "credentials.json"):
        load_installed_credentials()
        return
    raise RuntimeError(
        f"{CREDENTIALS_PATH} not found. Download OAuth Desktop credentials from "
        "Google Cloud Console, save as credentials.json, or set GOOGLE_CREDENTIALS secret."
    )


def save_token_json(creds) -> None:
    TOKEN_JSON_PATH.write_text(creds.to_json(), encoding="utf-8")
    log("auth", f"Saved refreshed token to {TOKEN_JSON_PATH}")


def load_token_pickle_creds():
    from google.oauth2.credentials import Credentials

    with open(TOKEN_PICKLE_PATH, "rb") as token_file:
        creds = pickle.load(token_file)
    if isinstance(creds, Credentials):
        save_token_json(creds)
        log("auth", "Migrated token.pickle → token.json")
        return creds
    raise RuntimeError("token.pickle format not recognized.")


def ensure_token_file() -> None:
    if TOKEN_JSON_PATH.exists():
        log("auth", f"Using {TOKEN_JSON_PATH}")
        return
    if TOKEN_PICKLE_PATH.exists():
        load_token_pickle_creds()
        return
    if decode_secret_to_file("GOOGLE_TOKEN", TOKEN_JSON_PATH, "token.json"):
        return
    if decode_secret_to_file("GOOGLE_TOKEN_JSON", TOKEN_JSON_PATH, "token.json"):
        return
    # Legacy: GOOGLE_TOKEN was base64 pickle
    raw = os.environ.get("GOOGLE_TOKEN")
    if raw:
        try:
            data = base64.b64decode(raw.strip())
            if data[:1] in (b"{", b"["):
                TOKEN_JSON_PATH.write_bytes(data)
                log("auth", "Decoded GOOGLE_TOKEN (JSON) → token.json")
                return
            TOKEN_PICKLE_PATH.write_bytes(data)
            log("auth", "Decoded legacy GOOGLE_TOKEN (pickle) → token.pickle")
            load_token_pickle_creds()
            return
        except Exception as exc:
            raise RuntimeError(f"Failed to decode GOOGLE_TOKEN: {exc}") from exc


def get_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    ensure_credentials_file()
    ensure_token_file()

    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_JSON_PATH), YOUTUBE_SCOPES)
    except Exception as exc:
        raise RuntimeError(f"Failed to load token.json: {exc}") from exc

    if creds.valid:
        log("auth", "OAuth token is valid.")
        return creds

    if creds.expired and creds.refresh_token:
        try:
            log("auth", "Refreshing expired OAuth token...")
            creds.refresh(Request())
            save_token_json(creds)
            log("auth", "Token refreshed successfully.")
            return creds
        except Exception as exc:
            log("auth", f"Token refresh failed ({exc}).")

    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        raise RuntimeError(
            "No valid YouTube token in CI. Run locally: python uploader.py --authenticate "
            "then update the GOOGLE_TOKEN secret with base64 of token.json."
        )

    log("auth", "Starting Desktop installed-app OAuth (loopback, no redirect URI setup)...")
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(CREDENTIALS_PATH),
            YOUTUBE_SCOPES,
        )
        creds = flow.run_local_server(
            host="127.0.0.1",
            port=0,
            open_browser=True,
            prompt="consent",
        )
        save_token_json(creds)
        log("auth", "OAuth complete. token.json saved.")
        return creds
    except Exception as exc:
        raise RuntimeError(f"OAuth flow failed: {exc}") from exc


def get_youtube_service():
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "Install dependencies: pip install -r requirements.txt"
        ) from exc

    creds = get_credentials()
    try:
        service = build("youtube", "v3", credentials=creds)
        log("auth", "YouTube Data API v3 client ready.")
        return service
    except Exception as exc:
        raise RuntimeError(f"Failed to build YouTube client: {exc}") from exc


def resolve_video_path() -> Path:
    if SHORT_PATH.exists():
        return SHORT_PATH
    if LEGACY_SHORT_PATH.exists():
        log("upload", f"Using legacy {LEGACY_SHORT_PATH.name}")
        return LEGACY_SHORT_PATH
    raise RuntimeError(
        f"{SHORT_PATH.name} not found. Run main.py first to create the video."
    )


def read_title() -> str:
    if not TITLE_PATH.exists():
        raise RuntimeError(f"{TITLE_PATH} not found. Run main.py first.")
    topic = TITLE_PATH.read_text(encoding="utf-8").strip()
    if not topic:
        raise RuntimeError("title.txt is empty.")
    return topic


def upload_short(youtube, title: str) -> str:
    from googleapiclient.http import MediaFileUpload

    video_path = resolve_video_path()
    log("upload", f"Video file: {video_path}")

    video_title = f"{title} #Shorts"
    if len(video_title) > 100:
        video_title = f"{title[:90]} #Shorts"

    log("upload", f"Uploading Short: {video_title}")

    body = {
        "snippet": {
            "title": video_title,
            "description": DESCRIPTION,
            "tags": SHORTS_TAGS,
            "categoryId": "27",
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
            "embeddable": True,
            "license": "youtube",
        },
    }

    try:
        media = MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            resumable=True,
            chunksize=1024 * 1024,
        )
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                progress = int(status.progress() * 100)
                log("upload", f"Upload progress: {progress}%")

        video_id = response.get("id")
        if not video_id:
            raise RuntimeError("Upload succeeded but no video ID returned.")

        shorts_url = f"https://www.youtube.com/shorts/{video_id}"
        watch_url = f"https://www.youtube.com/watch?v={video_id}"
        log("upload", f"Upload complete: {shorts_url}")
        log("upload", f"Watch URL: {watch_url}")
        return video_id
    except Exception as exc:
        raise RuntimeError(f"YouTube upload failed: {exc}") from exc


def cleanup_temp_files() -> None:
    log("cleanup", "Removing temporary files...")
    removed = 0

    if VOICE_PATH.exists():
        VOICE_PATH.unlink()
        removed += 1
        log("cleanup", f"Deleted {VOICE_PATH.name}")

    if CLIPS_DIR.exists():
        for clip in CLIPS_DIR.glob("*"):
            try:
                clip.unlink()
                removed += 1
            except Exception as exc:
                log("cleanup", f"Could not delete {clip.name}: {exc}")
        try:
            CLIPS_DIR.rmdir()
        except OSError:
            pass

    for optional in (SHORT_PATH, LEGACY_SHORT_PATH, TITLE_PATH):
        if optional.exists():
            try:
                optional.unlink()
                removed += 1
                log("cleanup", f"Deleted {optional.name}")
            except Exception as exc:
                log("cleanup", f"Could not delete {optional.name}: {exc}")

    log("cleanup", f"Cleanup finished ({removed} items removed).")


def run_authenticate() -> int:
    print("=== YouTube OAuth — credentials.json setup ===", flush=True)
    try:
        get_credentials()
        log("done", "Authentication successful. token.json is ready for uploads.")
        return 0
    except Exception as exc:
        log("error", str(exc))
        return 1


def run_upload() -> int:
    print("=== YouTube Shorts Uploader — starting ===", flush=True)
    try:
        youtube = get_youtube_service()
        title = read_title()
        upload_short(youtube, title)
        cleanup_temp_files()
        log("done", "Pipeline complete.")
        return 0
    except Exception as exc:
        log("error", str(exc))
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="YouTube Shorts OAuth and upload")
    parser.add_argument(
        "--authenticate",
        action="store_true",
        help="Run OAuth flow using credentials.json (creates token.json)",
    )
    args = parser.parse_args()
    if args.authenticate:
        return run_authenticate()
    return run_upload()


if __name__ == "__main__":
    sys.exit(main())
