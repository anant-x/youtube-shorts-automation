# One-time setup:
# 1. Google Cloud Console: enable YouTube Data API v3, create OAuth 2.0 Desktop credentials.
# 2. Run a local OAuth flow once to obtain token.pickle (google-auth-oauthlib installed):
#      from google_auth_oauthlib.flow import InstalledAppFlow
#      SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
#      flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
#      creds = flow.run_local_server(port=0)
#      pickle.dump(creds, open("token.pickle", "wb"))
# 3. Base64-encode token.pickle for GitHub: base64 -i token.pickle | pbcopy
# 4. Add GitHub secret GOOGLE_TOKEN with that base64 string.
# 5. Locally, place token.pickle in this directory OR set GOOGLE_TOKEN env var.

import base64
import os
import pickle
import sys
from pathlib import Path

WORK_DIR = Path(__file__).resolve().parent
SHORT_PATH = WORK_DIR / "short.mp4"
TITLE_PATH = WORK_DIR / "title.txt"
TOKEN_PATH = WORK_DIR / "token.pickle"
VOICE_PATH = WORK_DIR / "voice.mp3"
CLIPS_DIR = WORK_DIR / "clips"

DESCRIPTION = "Follow for daily facts!\n#shorts #facts #viral"
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def log(step: str, message: str) -> None:
    print(f"[{step}] {message}", flush=True)


def load_token_pickle() -> None:
    log("auth", "Loading YouTube OAuth token...")
    if TOKEN_PATH.exists():
        log("auth", f"Using existing {TOKEN_PATH}")
        return

    token_b64 = os.environ.get("GOOGLE_TOKEN")
    if not token_b64:
        raise RuntimeError(
            "No token.pickle found and GOOGLE_TOKEN env var is not set."
        )

    try:
        token_bytes = base64.b64decode(token_b64.strip())
        TOKEN_PATH.write_bytes(token_bytes)
        log("auth", "Decoded GOOGLE_TOKEN secret into token.pickle")
    except Exception as exc:
        raise RuntimeError(f"Failed to decode GOOGLE_TOKEN: {exc}") from exc


def get_youtube_service():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "google-api-python-client / google-auth not installed."
        ) from exc

    load_token_pickle()

    try:
        with open(TOKEN_PATH, "rb") as token_file:
            creds = pickle.load(token_file)
    except Exception as exc:
        raise RuntimeError(f"Failed to load token.pickle: {exc}") from exc

    if hasattr(creds, "expired") and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(TOKEN_PATH, "wb") as token_file:
                pickle.dump(creds, token_file)
            log("auth", "Refreshed expired OAuth token.")
        except Exception as exc:
            log("auth", f"Token refresh failed ({exc}); trying upload anyway.")

    try:
        return build("youtube", "v3", credentials=creds)
    except Exception as exc:
        raise RuntimeError(f"Failed to build YouTube client: {exc}") from exc


def read_title() -> str:
    if not TITLE_PATH.exists():
        raise RuntimeError(f"{TITLE_PATH} not found. Run main.py first.")
    topic = TITLE_PATH.read_text(encoding="utf-8").strip()
    if not topic:
        raise RuntimeError("title.txt is empty.")
    return topic


def upload_short(youtube, title: str) -> str:
    from googleapiclient.http import MediaFileUpload

    if not SHORT_PATH.exists():
        raise RuntimeError(f"{SHORT_PATH} not found. Run main.py first.")

    video_title = f"{title} #Shorts"
    log("upload", f"Uploading as: {video_title}")

    body = {
        "snippet": {
            "title": video_title,
            "description": DESCRIPTION,
            "categoryId": "27",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    try:
        media = MediaFileUpload(
            str(SHORT_PATH),
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
        url = f"https://www.youtube.com/watch?v={video_id}"
        log("upload", f"Upload complete: {url}")
        return url
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

    for optional in (SHORT_PATH, TITLE_PATH):
        if optional.exists():
            try:
                optional.unlink()
                removed += 1
                log("cleanup", f"Deleted {optional.name}")
            except Exception as exc:
                log("cleanup", f"Could not delete {optional.name}: {exc}")

    log("cleanup", f"Cleanup finished ({removed} items removed).")


def main() -> int:
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


if __name__ == "__main__":
    sys.exit(main())
