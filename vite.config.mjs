import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import fs from "node:fs";
import path from "node:path";

function readDotEnvValue(key) {
  const envPath = path.resolve(process.cwd(), ".env");
  if (!fs.existsSync(envPath)) return "";

  const lines = fs.readFileSync(envPath, "utf8").split(/\r?\n/);
  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const idx = line.indexOf("=");
    if (idx === -1) continue;

    const currentKey = line.slice(0, idx).trim();
    if (currentKey !== key) continue;

    let value = line.slice(idx + 1).trim();
    if (value.length >= 2 && value[0] === value[value.length - 1] && (value[0] === '"' || value[0] === "'")) {
      value = value.slice(1, -1);
    }
    return value;
  }

  return "";
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const googleMapsApiKey = (
    env.GOOGLE_MAPS_API ||
    env.VITE_GOOGLE_MAPS_API ||
    readDotEnvValue("GOOGLE_MAPS_API") ||
    readDotEnvValue("VITE_GOOGLE_MAPS_API") ||
    ""
  ).trim();

  return {
    plugins: [react()],
    define: {
      __GOOGLE_MAPS_API__: JSON.stringify(googleMapsApiKey),
    },
    server: {
      proxy: {
        "/api": "http://localhost:3000",
        "/config.js": "http://localhost:3000",
      },
    },
  };
});
