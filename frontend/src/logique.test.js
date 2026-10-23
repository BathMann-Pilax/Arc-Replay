import { describe, expect, it } from "vitest";
import {
  adresseTelecommande, camerasCommunes, camerasVisibles, codeDepuisAdresse, colonnesPour,
  impactsPositionnes, libelleScore, positionSurCible, rejouable, urlFichier,
} from "./logique";

const etat = {
  cameras: [{ id: "profil" }, { id: "face" }, { id: "cible" }],
  disposition: { ordre: ["cible", "profil", "face"], masquees: ["face"], focus: null },
};

describe("mosaïque", () => {
  it("suit l'ordre choisi et cache les vues masquées", () => {
    expect(camerasVisibles(etat).map((c) => c.id)).toEqual(["cible", "profil"]);
  });
  it("ignore une caméra disparue de la configuration", () => {
    const e = { ...etat, disposition: { ...etat.disposition, ordre: ["ancienne", "profil"] } };
    expect(camerasVisibles(e).map((c) => c.id)).toEqual(["profil"]);
  });
  it("choisit le nombre de colonnes", () => {
    expect([1, 2, 4, 5, 9].map(colonnesPour)).toEqual([1, 2, 2, 3, 3]);
  });
});

describe("fichiers", () => {
  it("encode chaque segment du chemin", () => {
    expect(urlFichier("2026-10-23_18h41m05/volee01/V01_F1 a.mp4"))
      .toBe("/fichiers/2026-10-23_18h41m05/volee01/V01_F1%20a.mp4");
  });
});

describe("scores et blason", () => {
  it("affiche X, M ou le score", () => {
    expect(libelleScore(null)).toBe("–");
    expect(libelleScore({ score: 10, x: true })).toBe("X");
    expect(libelleScore({ score: 0 })).toBe("M");
    expect(libelleScore({ score: 7 })).toBe("7");
  });
  it("ne place sur le blason que les impacts mesurés", () => {
    const imp = [{ x_mm: 1, y_mm: 2, diametre_mm: 400 }, { x_mm: null, y_mm: null, score: 9 }, null];
    expect(impactsPositionnes(imp)).toHaveLength(1);
  });
  it("convertit les millimètres en position SVG, y vers le haut", () => {
    expect(positionSurCible(0, 0, 400)).toMatchObject({ x: 50, y: 50 });
    expect(positionSurCible(200, 200, 400)).toMatchObject({ x: 100, y: 0 });
  });
});

describe("rejeu et comparaison", () => {
  const a = { clips: { profil: "a", cible: "b", face: "c" } };
  const b = { clips: { cible: "d", face: "e" } };
  it("ne rejoue pas une volée partie sur la clé", () => {
    expect(rejouable(a)).toBe(true);
    expect(rejouable({ ...a, archivee: true })).toBe(false);
    expect(rejouable({ clips: {} })).toBe(false);
  });
  it("propose les caméras communes visibles", () => {
    expect(camerasCommunes(etat, a, b).map((c) => c.id)).toEqual(["cible"]);
  });
});

describe("code de la télécommande", () => {
  it("prend le code de l'adresse en priorité", () => {
    expect(codeDepuisAdresse("?code=12%2034", "x")).toBe("12 34");
    expect(codeDepuisAdresse("", "x")).toBe("x");
    expect(codeDepuisAdresse("?controles", null)).toBe("");
  });
  it("met le code dans le QR code seulement s'il existe", () => {
    expect(adresseTelecommande("http://10.42.0.1", "")).toBe("http://10.42.0.1/telecommande");
    expect(adresseTelecommande("http://10.42.0.1", "a b")).toBe("http://10.42.0.1/telecommande?code=a%20b");
  });
});
