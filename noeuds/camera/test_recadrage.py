"""Calcul de la zone du capteur (sans Pi)."""

from recadrage import rectangle

# Caméra HQ (IMX477) : 4056 × 3040 pixels utiles
HQ = (0, 0, 4056, 3040)


def test_sans_zoom_garde_toute_la_largeur_en_16_9():
    x, y, l, h = rectangle(HQ, 16 / 9, 1, 0.5, 0.5)
    assert (x, l) == (0, 4056)
    assert abs(l / h - 16 / 9) < 0.01
    assert abs(y - (3040 - h) / 2) <= 2


def test_zoom_centre():
    x, y, l, h = rectangle(HQ, 16 / 9, 4, 0.5, 0.5)
    assert l == 1014 and abs(x + l / 2 - 2028) <= 2 and abs(y + h / 2 - 1520) <= 2


def test_zone_bornee_au_capteur():
    x, y, l, h = rectangle(HQ, 16 / 9, 4, 1.0, 0.0)
    assert x + l <= 4056 and y == 0


def test_capteur_decale_et_valeurs_paires():
    x, y, l, h = rectangle((16, 8, 4000, 3000), 4 / 3, 3, 0.2, 0.7)
    assert x >= 16 and y >= 8 and x + l <= 4016 and y + h <= 3008
    assert all(v % 2 == 0 for v in (x, y, l, h))


# --- zoom numérique fixe (streamer.calculer_recadrage, nœud cible) ----------

from streamer import calculer_recadrage  # noqa: E402


def test_zoom_fixe_centre_et_pair():
    x, y, l, h = calculer_recadrage(HQ, 3)
    assert (l, h) == (1352, 1012)
    assert abs(x + l / 2 - 2028) <= 1 and abs(y + h / 2 - 1520) <= 1
    assert l % 2 == 0 and h % 2 == 0


def test_zoom_fixe_inutile_sous_1():
    assert calculer_recadrage(HQ, 1) == HQ
    assert calculer_recadrage(HQ, 0.5) == HQ
