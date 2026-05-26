# YouTube Shorts Automation

Automatically creates a short video and uploads it to YouTube from GitHub Actions.

## Automatic Runs

The `Auto Shorts` workflow runs every 6 hours and can also be started manually from the Actions tab.

Required repository secrets for uploading:

- `GOOGLE_CREDENTIALS`: base64 of `credentials.json`
- `GOOGLE_TOKEN`: base64 of `token.json`

Optional repository secrets for better content generation:

- `GROQ_API_KEY`: creates AI scripts
- `PEXELS_API_KEY`: downloads stock video clips

If the optional secrets are missing, the bot now uses built-in scripts and generated video clips so the creation step can still run.

## First-Time YouTube Setup

1. Create a Google Cloud OAuth client of type `Desktop app`.
2. Download it as `credentials.json`.
3. Run `python uploader.py --authenticate` locally to create `token.json`.
4. Add both files to GitHub Actions secrets as base64 values:

```bash
base64 -i credentials.json | pbcopy
base64 -i token.json | pbcopy
```
