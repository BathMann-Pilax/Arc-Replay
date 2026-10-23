import { createRoot } from "react-dom/client";
import Ecran from "./Ecran";
import Telecommande from "./Telecommande";
import "./styles.css";

const page = location.pathname.startsWith("/telecommande") ? <Telecommande /> : <Ecran />;
document.body.classList.add(location.pathname.startsWith("/telecommande") ? "page-telecommande" : "page-ecran");

createRoot(document.getElementById("racine")).render(page);
