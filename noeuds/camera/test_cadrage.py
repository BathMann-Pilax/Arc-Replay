"""Cadrage, canal et réglages du nœud (sans Pi ni serveur)."""

import json

import pytest

from cadrage import Cadrage, Reglages, zone_maximale
from canal import Canal, repondre
from streamer import calculer_recadrage
from vue_cadree import parametres

# Caméra HQ (IMX477) : 4056 × 3040 pixels utiles
HQ = (0, 0, 4056, 3040)


def ratio(r):
    return r[2] / r[3]


# --- cadrage -----------------------------------------------------------------

def test_vue_complete_16_9_centree():
    x, y, l, h = Cadrage(HQ).rectangle()
    assert (x, l) == (0, 4056)
    assert abs(ratio((x, y, l, h)) - 16 / 9) < 0.01
    assert abs(y + h / 2 - 1520) <= 2
    assert all(v % 2 == 0 for v in (x, y, l, h))


def test_zoom_par_pas_de_1_25_et_centre():
    c = Cadrage(HQ)
    c.zoomer(pas=1)
    assert c.zoom == 1.25
    c.zoomer(pas=2)
    assert c.zoom == pytest.approx(1.25 ** 3, abs=1e-4)
    x, y, l, h = c.rectangle()
    assert abs(x + l / 2 - 2028) <= 2 and abs(y + h / 2 - 1520) <= 2
    assert abs(ratio((x, y, l, h)) - 16 / 9) < 0.01


def test_zoom_borne_entre_1_et_zoom_max():
    c = Cadrage(HQ, Reglages(zoom_max=8))
    c.zoomer(pas=50)
    assert c.zoom == 8
    assert c.rectangle()[2] == 4056 // 8 // 2 * 2
    c.zoomer(pas=-50)
    assert c.zoom == 1
    c.zoomer(facteur=3)
    assert c.zoom == 3


def test_retour_exact_apres_plus_puis_moins():
    c = Cadrage(HQ)
    for _ in range(4):
        c.zoomer(pas=1)
    for _ in range(4):
        c.zoomer(pas=-1)
    assert c.zoom == 1.0


def test_deplacement_de_10_pourcent_de_la_largeur_visible():
    c = Cadrage(HQ)
    c.zoomer(facteur=4)  # zone de 1014 px de large
    x0 = c.rectangle()[0]
    c.deplacer(dx=1)
    assert abs((c.rectangle()[0] - x0) - 101) <= 2
    y0 = c.rectangle()[1]
    c.deplacer(dy=-1)  # même pas en pixels vers le haut
    assert abs((y0 - c.rectangle()[1]) - 101) <= 2


def test_toujours_dans_le_capteur():
    c = Cadrage(HQ)
    c.zoomer(facteur=2)
    for _ in range(100):
        c.deplacer(dx=1, dy=1)
    x, y, l, h = c.rectangle()
    assert x + l <= 4056 and y + h <= 3040 and x > 0
    for _ in range(100):
        c.deplacer(dx=-1, dy=-1)
    assert c.rectangle()[:2] == (0, 0)
    c.zoomer(facteur=0.1)  # dézoom : la zone grandit mais reste dans le capteur
    x, y, l, h = c.rectangle()
    assert x >= 0 and y >= 0 and x + l <= 4056 and y + h <= 3040


def test_capteur_decale():
    c = Cadrage((16, 8, 4000, 3000), Reglages(ratio=4 / 3))
    c.zoomer(facteur=3)
    c.deplacer(dx=-99, dy=99)
    x, y, l, h = c.rectangle()
    assert x == 16 and y + h <= 3008


def test_reinitialiser_et_commandes():
    c = Cadrage(HQ)
    c.appliquer({"action": "zoomer", "pas": 3})
    c.appliquer({"action": "deplacer", "dx": 2, "dy": 1})
    assert c.zoom > 1 and c.cx > 0.5
    c.appliquer({"action": "reinitialiser"})
    assert (c.cx, c.cy, c.zoom) == (0.5, 0.5, 1.0)
    with pytest.raises(ValueError):
        c.appliquer({"action": "voler"})


def test_persistance(tmp_path):
    fichier = tmp_path / "sous" / "cadrage-cible.json"
    c = Cadrage(HQ)
    c.zoomer(facteur=3)
    c.deplacer(dx=2)
    c.sauver(fichier)
    relu = Cadrage.charger(fichier, HQ)
    assert (relu.cx, relu.cy, relu.zoom) == pytest.approx((c.cx, c.cy, c.zoom))
    assert relu.rectangle() == c.rectangle()
    assert not list(fichier.parent.glob("*.tmp"))


def test_fichier_absent_ou_abime(tmp_path):
    assert Cadrage.charger(tmp_path / "absent.json", HQ).zoom == 1
    abime = tmp_path / "abime.json"
    abime.write_text("{pas du json")
    assert Cadrage.charger(abime, HQ).zoom == 1
    hors_bornes = tmp_path / "hors.json"
    hors_bornes.write_text(json.dumps({"cx": 5, "cy": -1, "zoom": 99}))
    c = Cadrage.charger(hors_bornes, HQ, Reglages(zoom_max=8))
    x, y, l, h = c.rectangle()
    assert c.zoom == 8 and x + l <= 4056 and y >= 0


def test_etat_renvoye_au_serveur():
    e = Cadrage(HQ).etat()
    assert e["zoom"] == 1 and e["zoom_max"] == 8 and e["pas_zoom"] == 1.25
    assert e["rectangle"][2] == 4056 and e["capteur"] == list(HQ)


class FauxPicam:
    def __init__(self, maxi, controles=None):
        self.camera_properties = {"ScalerCropMaximum": maxi}
        self.camera_controls = controles or {}
        self.sensor_resolution = (4056, 3040)


def test_zone_maximale_avant_configuration():
    # Avant configure(), picamera2 renvoie (0, 0, 0, 0) : repli sur la taille du capteur
    assert zone_maximale(FauxPicam((0, 0, 0, 0))) == HQ
    assert zone_maximale(FauxPicam(None)) == HQ
    assert zone_maximale(FauxPicam((8, 16, 4040, 3008))) == (8, 16, 4040, 3008)
    # Propriété invalide mais bornes du contrôle ScalerCrop connues
    controles = {"ScalerCrop": ((0, 0, 64, 64), (0, 2, 4056, 3036), (0, 0, 4056, 3040))}
    assert zone_maximale(FauxPicam((0, 0, 0, 0), controles)) == (0, 2, 4056, 3036)


# --- canal -------------------------------------------------------------------

def test_reponse_a_une_commande():
    c = Cadrage(HQ)

    def traiter(cmd):
        c.appliquer(cmd)
        return c.etat()

    r = repondre(traiter, {"type": "commande", "id": 4, "commande": {"action": "zoomer", "pas": 1}})
    assert r["type"] == "reponse" and r["id"] == 4 and r["cadrage"]["zoom"] == 1.25
    r = repondre(traiter, {"type": "commande", "id": 5, "commande": {"action": "inconnue"}})
    assert r["id"] == 5 and "erreur" in r
    assert repondre(traiter, {"type": "config"}) is None
    assert "erreur" in repondre(None, {"type": "commande", "id": 6})


def test_canal_recoit_config_et_commande():
    canal = Canal("127.0.0.1:8080", "cible")
    assert canal.url == "ws://127.0.0.1:8080/api/noeud/ws?camera=cible"
    envoyes = []
    canal._envoyer = envoyes.append
    canal._recevoir({"type": "config", "camera": {"capteur": "binne"}})
    assert canal.attendre_config(0) == {"capteur": "binne"}
    vues = []
    canal.sur_config = vues.append
    canal._recevoir({"type": "config", "camera": {"capteur": "complet"}})
    assert vues == [{"capteur": "complet"}]
    canal.traiter = lambda cmd: {"zoom": 2}
    canal._recevoir({"type": "commande", "id": 1, "commande": {"action": "zoomer"}})
    assert envoyes[-1] == {"type": "reponse", "id": 1, "cadrage": {"zoom": 2}}


# --- réglages du flux ----------------------------------------------------------

def test_reglages_du_serveur_prioritaires():
    p = parametres({"capteur": "binne", "largeur": 1280, "hauteur": 720, "debit": 3_000_000}, None)
    assert p["capteur"] == "binne" and p["fps"] == 30 and p["largeur"] == 1280
    p = parametres({"capteur": "binne"}, {"capteur": "complet", "largeur": 1920, "hauteur": 1080,
                                          "debit": 4_000_000, "cadrage": {"zoom_max": 6}})
    assert p["capteur"] == "complet" and p["fps"] == 10 and p["cadrage"] == {"zoom_max": 6}
    assert parametres({}, {"fps": 15})["fps"] == 15
    assert parametres({"capteur": "n'importe"}, None)["capteur"] == "complet"


# --- zoom numérique fixe (nœud cible en mode détection) --------------------------

def test_zoom_fixe_centre_et_pair():
    x, y, l, h = calculer_recadrage(HQ, 3)
    assert (l, h) == (1352, 1012)
    assert abs(x + l / 2 - 2028) <= 1 and abs(y + h / 2 - 1520) <= 1


def test_zoom_fixe_inutile_sous_1():
    assert calculer_recadrage(HQ, 1) == HQ
