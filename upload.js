#!/usr/bin/env node
/**
 * YouTube Shorts upload — Google OAuth Desktop (installed app) flow.
 * Uses dynamic loopback (127.0.0.1:random port). No redirect URIs to add in Console.
 *
 * Setup: credentials.json (Desktop client) → node app.js --authenticate
 * CI: GOOGLE_CREDENTIALS + GOOGLE_TOKEN secrets (base64)
 */

const fs = require("fs");
const path = require("path");
const http = require("http");
const { exec } = require("child_process");
const { google } = require("googleapis");

const WORK_DIR = __dirname;
const CREDENTIALS_PATH = path.join(WORK_DIR, "credentials.json");
const TOKEN_PATH = path.join(WORK_DIR, "token.json");
const SHORT_PATH = path.join(WORK_DIR, "shorts.mp4");
const LEGACY_SHORT_PATH = path.join(WORK_DIR, "short.mp4");
const TITLE_PATH = path.join(WORK_DIR, "title.txt");

const SCOPES = ["https://www.googleapis.com/auth/youtube.upload"];
const DESCRIPTION = "Follow for daily facts!\n#shorts #facts #viral";
const SHORTS_TAGS = ["shorts", "facts", "viral", "youtubeshorts"];
const AUTH_TIMEOUT_MS = 180000;

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
    "credentials.json not found. Download OAuth credentials for a Desktop application."
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
  throw new Error("token.json not found. Run: node app.js --authenticate");
}

/** Desktop OAuth client from credentials.json (installed app, not web). */
function loadInstalledConfig() {
  ensureCredentialsFile();
  const keys = JSON.parse(fs.readFileSync(CREDENTIALS_PATH, "utf8"));

  if (keys.web && !keys.installed) {
    throw new Error(
      "credentials.json is a Web client. Create an OAuth client of type " +
        "'Desktop app' in Google Cloud Console and download the new JSON."
    );
  }

  const config = keys.installed;
  if (!config || !config.client_id || !config.client_secret) {
    throw new Error(
      "credentials.json must contain an 'installed' Desktop OAuth block."
    );
  }

  log("auth", "Using Google OAuth Desktop (installed application) client.");
  return config;
}

function createOAuth2Client(config, redirectUri) {
  return new google.auth.OAuth2(
    config.client_id,
    config.client_secret,
    redirectUri
  );
}

function openBrowser(url) {
  const cmd =
    process.platform === "darwin"
      ? `open "${url}"`
      : process.platform === "win32"
        ? `start "" "${url}"`
        : `xdg-open "${url}"`;
  exec(cmd, (err) => {
    if (err) {
      log("auth", "Could not open browser automatically — open the URL printed above.");
    }
  });
}

/**
 * Installed-app loopback flow (Google recommended for Desktop clients).
 * 127.0.0.1 + ephemeral port — no manual redirect URI registration required.
 */
function authenticateInstalledApp() {
  const config = loadInstalledConfig();

  return new Promise((resolve, reject) => {
    let oauth2Client;
    let redirectUri;
    let timeoutId;

    const server = http.createServer(async (req, res) => {
      try {
        const query = new URL(req.url || "/", "http://127.0.0.1").searchParams;

        if (query.get("error")) {
          res.end("Authentication failed. Return to the terminal.");
          server.close();
          reject(
            new Error(
              query.get("error_description") || query.get("error") || "OAuth denied"
            )
          );
          return;
        }

        const code = query.get("code");
        if (!code) {
          res.writeHead(404);
          res.end();
          return;
        }

        res.end(
          "<h2>Authentication successful</h2><p>You can close this tab.</p>"
        );
        clearTimeout(timeoutId);
        server.close();

        const { tokens } = await oauth2Client.getToken({ code, redirect_uri: redirectUri });
        oauth2Client.setCredentials(tokens);
        fs.writeFileSync(TOKEN_PATH, JSON.stringify(tokens, null, 2));
        log("auth", `Saved token to ${TOKEN_PATH}`);
        resolve(oauth2Client);
      } catch (err) {
        server.close();
        reject(err);
      }
    });

    server.listen(0, "127.0.0.1", () => {
      const port = server.address().port;
      redirectUri = `http://127.0.0.1:${port}`;
      oauth2Client = createOAuth2Client(config, redirectUri);

      const authUrl = oauth2Client.generateAuthUrl({
        access_type: "offline",
        scope: SCOPES,
        prompt: "consent",
      });

      log(
        "auth",
        "Installed app OAuth — loopback redirect (no Console redirect URI setup)"
      );
      log("auth", `Listening on ${redirectUri}`);
      openBrowser(authUrl);

      timeoutId = setTimeout(() => {
        server.close();
        reject(new Error("OAuth timed out after 3 minutes."));
      }, AUTH_TIMEOUT_MS);
    });

    server.on("error", reject);
  });
}

async function getAuthorizedClient() {
  const config = loadInstalledConfig();
  ensureTokenFile();

  const redirectUri =
    (config.redirect_uris && config.redirect_uris[0]) || "http://127.0.0.1";
  const oauth2Client = createOAuth2Client(config, redirectUri);
  oauth2Client.setCredentials(JSON.parse(fs.readFileSync(TOKEN_PATH, "utf8")));

  try {
    const access = await oauth2Client.getAccessToken();
    if (!access || !access.token) {
      throw new Error("No access token");
    }
    log("auth", "OAuth token is valid.");
    fs.writeFileSync(TOKEN_PATH, JSON.stringify(oauth2Client.credentials, null, 2));
    return oauth2Client;
  } catch (err) {
    if (process.env.CI || process.env.GITHUB_ACTIONS) {
      throw new Error(
        "Invalid token in CI. Run locally: node app.js --authenticate"
      );
    }
    log("auth", `Token invalid (${err.message}); starting installed app flow...`);
    return authenticateInstalledApp();
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

function resolveVideoPath() {
  if (fs.existsSync(SHORT_PATH)) return SHORT_PATH;
  if (fs.existsSync(LEGACY_SHORT_PATH)) {
    log("upload", `Using legacy ${path.basename(LEGACY_SHORT_PATH)}`);
    return LEGACY_SHORT_PATH;
  }
  throw new Error("shorts.mp4 not found. Run: python main.py");
}

async function uploadShort(auth) {
  const videoPath = resolveVideoPath();
  log("upload", `Video file: ${videoPath}`);

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
      body: fs.createReadStream(videoPath),
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
      console.log("=== YouTube OAuth — Desktop installed app ===");
      await authenticateInstalledApp();
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
