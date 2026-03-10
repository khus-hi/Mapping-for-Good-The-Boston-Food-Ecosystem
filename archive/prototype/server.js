
/*
**** IMPORTANT*****
This file is replaced by app.py

*/



const http = require("http");
const fs = require("fs");
const path = require("path");

const ROOT = __dirname;
const PORT = Number(process.env.PORT || 3000);

function parseDotEnv(filePath) {
  const env = {};
  if (!fs.existsSync(filePath)) return env;

  const lines = fs.readFileSync(filePath, "utf8").split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const match = trimmed.match(/^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/);
    if (!match) continue;

    const key = match[1];
    let value = match[2].trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    env[key] = value;
  }
  return env;
}

const dotEnv = parseDotEnv(path.join(ROOT, ".env"));
const googleMapsApiKey = process.env.GOOGLE_MAPS_API || dotEnv.GOOGLE_MAPS_API || "";

const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".geojson": "application/geo+json; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
};

function sendFile(res, filePath) {
  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
      res.end("Not Found");
      return;
    }

    const ext = path.extname(filePath).toLowerCase();
    const contentType = contentTypes[ext] || "application/octet-stream";
    res.writeHead(200, { "Content-Type": contentType });
    res.end(data);
  });
}

function resolvePublicPath(urlPath) {
  const normalized = path.normalize(urlPath).replace(/^(\.\.[/\\])+/, "");
  const localPath = normalized === "/" ? "/index.html" : normalized;
  return path.join(ROOT, localPath);
}

const server = http.createServer((req, res) => {
  const reqPath = (req.url || "/").split("?")[0];

  if (reqPath === "/config.js") {
    const payload = `window.APP_CONFIG = ${JSON.stringify({
      GOOGLE_MAPS_API_KEY: googleMapsApiKey,
    })};`;
    res.writeHead(200, { "Content-Type": "application/javascript; charset=utf-8" });
    res.end(payload);
    return;
  }

  const fullPath = resolvePublicPath(reqPath);
  if (!fullPath.startsWith(ROOT)) {
    res.writeHead(403, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("Forbidden");
    return;
  }

  sendFile(res, fullPath);
});

server.listen(PORT, () => {
  console.log(`Boston map app running at http://localhost:${PORT}`);
});
