# YouTube Shorts Automation

[![Auto Shorts](https://github.com/anant-x/youtube-shorts-automation/actions/workflows/upload.yml/badge.svg)](https://github.com/anant-x/youtube-shorts-automation/actions/workflows/upload.yml)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Node.js](https://img.shields.io/badge/Node.js-18%2B-339933?logo=nodedotjs&logoColor=white)](https://nodejs.org/)

Generate a vertical short-form video, create a voice-over, and upload the finished Short to YouTube. The pipeline can run locally or every six hours through GitHub Actions.

## How It Works

```text
Trending or fallback topic
        ↓
Groq script or built-in fallback
        ↓
Edge TTS voice-over
        ↓
Pexels clips or generated fallback clips
        ↓
MoviePy + FFmpeg 1080×1920 video
        ↓
YouTube Data API upload
```

The optional Groq and Pexels integrations improve the generated content. If either service is unavailable, the creation stage falls back to built-in scripts and generated video clips.

## Features

- Selects topics with Google Trends and a built-in fallback list
- Generates 55–65 word scripts with Groq when an API key is available
- Creates narration with Microsoft Edge TTS voices
- Downloads portrait stock footage from Pexels or generates local color clips
- Produces 1080×1920 H.264 videos with AAC audio
- Uploads public Shorts through YouTube OAuth
- Supports local Python or Node.js upload paths
- Runs manually or on a six-hour GitHub Actions schedule

## Requirements

- Python 3.11
- Node.js 18 or later if using the Node.js uploader
- FFmpeg available on your system path
- A Google Cloud project with YouTube Data API v3 enabled
- An OAuth 2.0 client of type **Desktop app**

Optional API keys:

- `GROQ_API_KEY` for AI-generated scripts
- `PEXELS_API_KEY` for portrait stock footage

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/anant-x/youtube-shorts-automation.git
cd youtube-shorts-automation

python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm install
```

Install FFmpeg if needed:

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get update && sudo apt-get install -y ffmpeg
```

### 2. Add optional content APIs

Create a local `.env` file if you want Groq scripts or Pexels clips:

```dotenv
GROQ_API_KEY=your_groq_key
PEXELS_API_KEY=your_pexels_key
```

Do not commit `.env`, `credentials.json`, or `token.json`. They are already excluded by `.gitignore`.

### 3. Create a Short

```bash
source .venv/bin/activate
python main.py
```

This creates `shorts.mp4` and `title.txt` in the repository directory.

### 4. Configure YouTube OAuth

1. Enable **YouTube Data API v3** in Google Cloud Console.
2. Configure the OAuth consent screen.
3. Create an OAuth client of type **Desktop app**.
4. Download the client file as `credentials.json` in the repository root.
5. Authenticate with one of the supported uploaders:

```bash
# Python uploader used by GitHub Actions
python uploader.py --authenticate

# Or Node.js uploader used by run.sh
npm run auth
```

The authentication flow creates `token.json`.

### 5. Upload

```bash
# Python
python uploader.py

# Or Node.js
npm run upload
```

Uploads are public by default. Review the `privacyStatus` setting in the uploader before testing on a production channel.

## One-Command Local Run

On macOS with Homebrew Python 3.11 installed:

```bash
chmod +x run.sh
./run.sh
```

`run.sh` loads `.env`, creates the video, and uploads it with the Node.js uploader.

## GitHub Actions

The [Auto Shorts workflow](.github/workflows/upload.yml) runs every six hours and can also be started from the Actions tab with **Run workflow**.

Add these repository secrets under **Settings → Secrets and variables → Actions**:

| Secret | Required | Purpose |
| --- | --- | --- |
| `GOOGLE_CREDENTIALS` | Yes | Base64-encoded `credentials.json` |
| `GOOGLE_TOKEN` | Yes | Base64-encoded `token.json` |
| `GROQ_API_KEY` | No | AI-generated scripts |
| `PEXELS_API_KEY` | No | Pexels stock video clips |

Encode the OAuth files:

```bash
# macOS
base64 -i credentials.json | pbcopy
base64 -i token.json | pbcopy

# Linux
base64 -w 0 credentials.json
base64 -w 0 token.json
```

OAuth refresh tokens can expire or be revoked. Re-run the local authentication step and replace `GOOGLE_TOKEN` if CI starts reporting token errors.

## Generated Files

| Path | Purpose |
| --- | --- |
| `shorts.mp4` | Final vertical video |
| `title.txt` | Topic used for the YouTube title |
| `voice.mp3` | Temporary narration audio |
| `clips/` | Downloaded or generated temporary footage |

Generated media and OAuth files are ignored by Git.

## Project Structure

```text
.
├── .github/workflows/upload.yml  # Scheduled CI pipeline
├── main.py                       # Topic, script, voice, and video generation
├── uploader.py                   # Python OAuth and YouTube uploader
├── app.js                        # Node.js upload entry point
├── upload.js                     # Node.js OAuth and YouTube uploader
├── run.sh                        # Local end-to-end helper for macOS
├── requirements.txt              # Python dependencies
├── package.json                  # Node.js dependencies and scripts
└── credentials.json.example      # OAuth credential shape example
```

## Troubleshooting

- **`ffmpeg` not found:** install FFmpeg and confirm `ffmpeg -version` works.
- **MoviePy import errors:** recreate the virtual environment with Python 3.11 and reinstall `requirements.txt`.
- **OAuth client rejected:** confirm `credentials.json` contains an `installed` block from a Desktop app client.
- **Missing video or title:** run `python main.py` before the uploader.
- **GitHub Actions token failure:** authenticate locally again and update the base64 `GOOGLE_TOKEN` secret.
- **API rate limits or outages:** omit the optional API key to use the built-in fallback path.

## Security Notes

- Never commit OAuth credentials, refresh tokens, or API keys.
- Use repository secrets for all CI credentials.
- Test with a non-critical YouTube channel before enabling the schedule.
- Review generated content before publishing if your channel requires editorial approval.

## License

No open-source license has been selected yet. Until a license file is added, the repository remains all rights reserved by its owner.
