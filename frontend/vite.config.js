import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import legacy from "@vitejs/plugin-legacy";

// En développement : `npm run dev` avec le back-end sur :8000 et MediaMTX sur :8888
const backend = process.env.ARC_BACKEND || "http://localhost:8000";
const hls = process.env.ARC_HLS || "http://localhost:8888";

// Version « mode solo » seule, publiée en https (GitHub Pages) : VITE_SOLO=1.
// Elle s'installe comme une application et marche hors ligne.
const solo = process.env.VITE_SOLO === "1";
const enTetesSolo = {
  name: "entetes-solo",
  transformIndexHtml: (html) => solo
    ? html
      .replace("<title>Arc Replay</title>", "<title>Arc Replay solo</title>")
      .replace("</head>", `    <link rel="manifest" href="./manifest.webmanifest" />
    <link rel="apple-touch-icon" href="./apple-touch-icon.png" />
  </head>`)
    : html,
};

export default defineConfig({
  plugins: [
    react(),
    enTetesSolo,
    // Version de secours pour les vieux navigateurs (iPad 2 : iOS 9, Safari 9).
    // Ils ignorent <script type="module"> et chargent cette version traduite en ES5,
    // les navigateurs récents gardent la version moderne.
    legacy({
      targets: ["defaults", "safari >= 9", "ios >= 9"],
      additionalLegacyPolyfills: ["whatwg-fetch"], // fetch arrive avec Safari 10.1
    }),
  ],
  build: {
    chunkSizeWarningLimit: 1000, // hls.js pèse à lui seul ~500 ko
    cssTarget: ["safari9", "chrome87", "firefox78"], // préfixes et syntaxe CSS compatibles iOS 9
  },
  // Adresses relatives : la version solo marche quel que soit le dossier d'hébergement
  base: solo ? "./" : "/",
  server: {
    host: true,
    proxy: {
      "/api": { target: backend, ws: true },
      "/hls": {
        target: hls,
        rewrite: (p) => p.replace(/^\/hls/, ""),
        // MediaMTX redirige vers /camera/index.m3u8?cookieCheck=1 : on garde le préfixe
        configure: (proxy) =>
          proxy.on("proxyRes", (res) => {
            const loc = res.headers.location;
            if (loc && loc.startsWith("/")) res.headers.location = "/hls" + loc;
          }),
      },
      "/fichiers": { target: backend },
      // WebRTC (WHEP de la vue directe, WHIP des téléphones) : signalement vers MediaMTX
      "/webrtc": {
        target: process.env.ARC_WEBRTC || "http://localhost:8889",
        rewrite: (p) => p.replace(/^\/webrtc/, ""),
        configure: (proxy) =>
          proxy.on("proxyRes", (res) => {
            const loc = res.headers.location;
            if (loc && loc.startsWith("/")) res.headers.location = "/webrtc" + loc;
          }),
      },
    },
  },
});
