import { createRoot } from "react-dom/client";
import "./styles.css";

// Version « mode solo » publiée seule (https) : VITE_SOLO=1 au moment de la construction
const solo = import.meta.env.VITE_SOLO === "1" || location.pathname.startsWith("/solo");
const telecommande = !solo && location.pathname.startsWith("/telecommande");

// Chaque page est chargée à la demande : le mode solo n'embarque pas le lecteur HLS
const page = solo ? import("./solo/Solo") : telecommande ? import("./Telecommande") : import("./Ecran");
document.body.classList.add(telecommande ? "page-telecommande" : "page-ecran");

if (solo && "serviceWorker" in navigator && window.isSecureContext) {
  // Hors ligne : l'application est gardée en cache après la première visite
  navigator.serviceWorker.register("./sw.js").then(() => navigator.serviceWorker.ready).then((reg) => {
    const fichiers = performance.getEntriesByType("resource").map((e) => e.name)
      .filter((u) => u.startsWith(location.origin));
    reg.active?.postMessage({ type: "precharger", fichiers: [location.href.split("#")[0], ...fichiers] });
  }).catch(() => {});
}

page.then(({ default: Page }) => createRoot(document.getElementById("racine")).render(<Page />));
