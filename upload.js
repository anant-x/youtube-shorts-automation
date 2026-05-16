#!/usr/bin/env node
/**
 * YouTube Shorts upload via googleapis + credentials.json (Node alternative).
 * Setup: place credentials.json, run `node upload.js --authenticate`, then upload.
 *
 * Env (GitHub Actions): GOOGLE_CREDENTIALS, GOOGLE_TOKEN (base64)
 */

const fs = require("fs");
const path = require("path");
const http = require("http");
const { google } = require("googleapis");

const WORK_DIR = __dirname;
const CREDENTIALS_PATH = path.join(WORK_DIR, "credentials.json");
const TOKEN_PATH = path.join(WORK_DIR, "token.json");
const SHORT_PATH = path.join(WORK_DIR, "short.mp4");
const TITLE_PATH = path.join(WORK_DIR, "title.txt");

const SCOPES = ["https://www.googleapis.com/auth/youtube.upload"];
const DESCRIPTION = "Follow for daily facts!\n#shorts #facts #viral";
const SHORTS_TAGS = ["shorts", "facts", "viral", "youtubeshorts"];

function log(step, message) {
  console.log(`[${step}] ${message}`);
}

function decodeSecret(envName, destPath, label) {
  const raw = process.env[envName];
  if (!raw) return false;
  fs.writeFileSync(destPath, Buffer.from(raw.trim(), "base64"));
  log("auth", `Wrote ${label} from ${envName}`);
  return true;
}

function ensureCredentialsFile() {
  if (fs.existsSync(CREDENTIALS_PATH)) {
    log("auth", `Using ${CREDENTIALS_PATH}`);
    return;
  }
  if (
    decodeSecret("GOOGLE_CREDENTIALS", CREDENTIALS_PATH, "credentials.json") ||
    decodeSecret("GOOGLE_CREDENTIALS_JSON", CREDENTIALS_PATH, "credentials.json")
  ) {
    return;
  }
  throw new Error(
    "credentials.json not found. Download OAuth Desktop JSON from Google Cloud Console."
  );
}

function ensureTokenFile() {
  if (fs.existsSync(TOKEN_PATH)) {
    log("auth", `Using ${TOKEN_PATH}`);
    return;
  }
  if (
    decodeSecret("GOOGLE_TOKEN", TOKEN_PATH, "token.json") ||
    decodeSecret("GOOGLE_TOKEN_JSON", TOKEN_PATH, "token.json")
  ) {
    return;
  }
  throw new Error("token.json not found. Run: node upload.js --authenticate");
}

function loadOAuthClient() {
  ensureCredentialsFile();
  const keys = JSON.parse(fs.readFileSync(CREDENTIALS_PATH, "utf8"));
  const config = keys.installed || keys.web;
  if (!config) {
    throw new Error("credentials.json must contain installed or web OAuth config.");
  }
  return new google.auth.OAuth2(
    config.client_id,
    config.client_secret,
    (config.redirect_uris && config.redirect_uris[0]) || "http://localhost"
  );
}

async function authorizeInteractive(oauth2Client) {
  const authUrl = oauth2Client.generateAuthUrl({
    access_type: "offline",
    scope: SCOPES,
    prompt: "consent",
  });

  log("auth", "Open this URL in your browser:");
  console.log(authUrl);

  const code = await new Promise((resolve, reject) => {
    const server = http.createServer((req, res) => {
      try {
        const url = new URL(req.url, "http://localhost");
        const authCode = url.searchParams.get("code");
        if (authCode) {
          res.end("Authentication successful. You can close this tab.");
          server.close();
          resolve(authCode);
        }
      } catch (err) {
        reject(err);
      }
    });
    server.listen(8080, () => log("auth", "Waiting for OAuth callback on http://localhost:8080"));
    setTimeout(() => {
      server.close();
      reject(new Error("OAuth timed out after 120s"));
    }, 120000);
  });

  const { tokens } = await oauth2Client.getToken(code);
  oauth2Client.setCredentials(tokens);
  fs.writeFileSync(TOKEN_PATH, JSON.stringify(tokens, null, 2));
  log("auth", `Saved token to ${TOKEN_PATH}`);
  return oauth2Client;
}

async function getAuthorizedClient() {
  const oauth2Client = loadOAuthClient();
  ensureTokenFile();
  oauth2Client.setCredentials(JSON.parse(fs.readFileSync(TOKEN_PATH, "utf8")));

  try {
    const token = await oauth2Client.getAccessToken();
    if (!token || !token.token) {
      throw new Error("No access token");
    }
    log("auth", "OAuth token is valid.");
    fs.writeFileSync(TOKEN_PATH, JSON.stringify(oauth2Client.credentials, null, 2));
    return oauth2Client;
  } catch (err) {
    if (process.env.CI || process.env.GITHUB_ACTIONS) {
      throw new Error(
        "Invalid token in CI. Run locally: node upload.js --authenticate"
      );
    }
    return authorizeInteractive(oauth2Client);
  }
}

function readTitle() {
  if (!fs.existsSync(TITLE_PATH)) {
    throw new Error("title.txt not found. Run main.py first.");
  }
  const title = fs.readFileSync(TITLE_PATH, "utf8").trim();
  if (!title) throw new Error("title.txt is empty.");
  return title;
}

async function uploadShort(auth) {
  if (!fs.existsSync(SHORT_PATH)) {
    throw new Error("short.mp4 not found. Run main.py first.");
  }

  const topic = readTitle();
  let videoTitle = `${topic} #Shorts`;
  if (videoTitle.length > 100) videoTitle = `${topic.slice(0, 90)} #Shorts`;

  log("upload", `Uploading Short: ${videoTitle}`);

  const youtube = google.youtube({ version: "v3", auth });
  const res = await youtube.videos.insert({
    part: ["snippet", "status"],
    requestBody: {
      snippet: {
        title: videoTitle,
        description: DESCRIPTION,
        tags: SHORTS_TAGS,
        categoryId: "27",
        defaultLanguage: "en",
      },
      status: {
        privacyStatus: "public",
        selfDeclaredMadeForKids: false,
        embeddable: true,
        license: "youtube",
      },
    },
    media: {
      body: fs.createReadStream(SHORT_PATH),
    },
  });

  const videoId = res.data.id;
  log("upload", `Upload complete: https://www.youtube.com/shorts/${videoId}`);
  return videoId;
}

async function main() {
  const authenticate = process.argv.includes("--authenticate");

  try {
    if (authenticate) {
      console.log("=== YouTube OAuth (googleapis) ===");
      const client = loadOAuthClient();
      await authorizeInteractive(client);
      log("done", "Authentication successful.");
      return;
    }

    console.log("=== YouTube Shorts Upload (googleapis) ===");
    const auth = await getAuthorizedClient();
    await uploadShort(auth);
    log("done", "Upload complete.");
  } catch (err) {
    log("error", err.message);
    process.exit(1);
  }
}

main();
