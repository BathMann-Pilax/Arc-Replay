import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// En développement : `npm run dev` avec le back-end sur :8000 et MediaMTX sur :8888
const backend = process.env.ARC_BACKEND || "http://localhost:8000";
const hls = process.env.ARC_HLS || "http://localhost:8888";

export default defineConfig({
  plugins: [react()],
  build: { chunkSizeWarningLimit: 1000 }, // hls.js pèse à lui seul ~500 ko
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
    },
  },
});
