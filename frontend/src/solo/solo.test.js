import { describe, expect, it } from "vitest";
import { dureeAGarder, indiceDansClip, Tampon } from "./tampon";
import { DetecteurLacher, niveauDbfs } from "./son";
import { annulerDerniere, avecImages, nouvelleVolee, seanceVide, tirer } from "./seance";

const image = (t) => ({ size: 10, t });

describe("tampon d'images", () => {
  it("garde l'ordre même si un encodage finit en retard", () => {
    const tp = new Tampon();
    tp.ajouter(0, image(0));
    tp.ajouter(66, image(66));
    tp.ajouter(33, image(33));
    expect(tp.images.map((i) => i.t)).toEqual([0, 33, 66]);
    expect(tp.octets).toBe(30);
  });
  it("trouve l'image à afficher en différé", () => {
    const tp = new Tampon();
    [0, 33, 66, 100].forEach((t) => tp.ajouter(t, image(t)));
    expect(tp.aLHeure(-1)).toBeNull();
    expect(tp.aLHeure(50).t).toBe(33);
    expect(tp.aLHeure(1000).t).toBe(100);
  });
  it("purge l'ancien et extrait un clip", () => {
    const tp = new Tampon();
    for (let t = 0; t <= 1000; t += 100) tp.ajouter(t, image(t));
    expect(tp.extraire(200, 400).map((i) => i.t)).toEqual([200, 300, 400]);
    tp.purger(500);
    expect(tp.images[0].t).toBe(500);
    expect(tp.octets).toBe(60);
    expect(tp.duree).toBe(500);
  });
  it("garde assez d'historique pour le retard et pour un clip", () => {
    expect(dureeAGarder({ delai_s: 10, avant_s: 6, apres_s: 3 })).toBe(13000);
    expect(dureeAGarder({ delai_s: 3, avant_s: 6, apres_s: 3 })).toBe(12000);
  });
  it("boucle dans un clip", () => {
    const im = [0, 100, 200, 300].map((t) => ({ t: 1000 + t }));
    expect(indiceDansClip(im, 0)).toBe(0);
    expect(indiceDansClip(im, 150)).toBe(1);
    expect(indiceDansClip(im, 300)).toBe(0); // boucle
    expect(indiceDansClip([], 10)).toBe(-1);
  });
});

describe("détection du lâcher", () => {
  it("mesure le niveau crête", () => {
    expect(niveauDbfs([0, 0.5, -1])).toBeCloseTo(0);
    expect(niveauDbfs(new Float32Array(4))).toBeCloseTo(-120);
  });
  it("ignore les rebonds", () => {
    const d = new DetecteurLacher(-20, 2000);
    expect(d.bloc(-10, 0)).toBe(true);
    expect(d.bloc(-10, 500)).toBe(false);
    expect(d.bloc(-30, 3000)).toBe(false);
    expect(d.bloc(-5, 3000)).toBe(true);
  });
});

describe("volées du mode solo", () => {
  it("numérote, ignore les rebonds et change de volée", () => {
    let s = seanceVide();
    const ids = [];
    for (let i = 0; i < 7; i++) {
      const r = tirer(s, i * 10000);
      s = r.seance;
      ids.push(r.fleche.id);
    }
    expect(ids.slice(0, 2)).toEqual(["V01_F1", "V01_F2"]);
    expect(ids[6]).toBe("V02_F1");
    expect(s.fleches).toHaveLength(1); // volée précédente oubliée
    expect(tirer(s, 61000)).toBeNull(); // anti-rebond
  });
  it("ouvre une volée après une longue pause", () => {
    let s = tirer(seanceVide(), 0).seance;
    expect(tirer(s, 200000).fleche.id).toBe("V02_F1");
  });
  it("annule la dernière flèche et reprend son numéro", () => {
    let s = tirer(seanceVide(), 0).seance;
    s = tirer(s, 10000).seance;
    s = annulerDerniere(s);
    expect(s.fleches.map((f) => f.id)).toEqual(["V01_F1"]);
    expect(tirer(s, 20000).fleche.id).toBe("V01_F2");
  });
  it("nouvelle volée manuelle et anti-rebond juste après", () => {
    let s = tirer(seanceVide(), 0).seance;
    s = nouvelleVolee(s);
    expect(s.fleches).toEqual([]);
    expect(tirer(s, 500)).toBeNull();
    expect(tirer(s, 5000).fleche.id).toBe("V02_F1");
  });
  it("range les images d'un clip", () => {
    let s = tirer(seanceVide(), 0).seance;
    s = avecImages(s, "V01_F1", [1, 2]);
    expect(s.fleches[0].images).toEqual([1, 2]);
  });
});
