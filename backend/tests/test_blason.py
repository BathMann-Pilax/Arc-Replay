import math

from app import blason as bl

B40 = bl.Blason(diametre_mm=400)  # zones de 20 mm, X de 10 mm de rayon


def score(b, x, y, **kw):
    r = bl.score_fleche(b, x, y, **kw)
    return bl.libelle(r["score"], r["x"])


def test_blason_simple_et_regle_de_la_ligne():
    assert score(B40, 0, 0) == "X"
    assert score(B40, 12.5, 0) == "X"     # le tube (rayon 2,5 mm) touche la ligne du X
    assert score(B40, 13, 0) == "10"
    assert score(B40, 22.5, 0) == "10"    # touche la ligne 10/9 : zone supérieure
    assert score(B40, 23, 0) == "9"
    assert score(B40, 0, -190) == "1"
    assert score(B40, 0, -203) == "M"     # hors blason
    # Même règle avec un tube plus gros
    assert score(B40, 24, 0, rayon_fleche_mm=4.5) == "10"


def test_a_confirmer_pres_d_une_ligne():
    r = bl.score_fleche(B40, 21.5, 0)      # bord à 19 mm : 1 mm de la ligne 10/9
    assert (r["score"], r["doute"], r["alternative"]) == (10, True, "9")
    r = bl.score_fleche(B40, 30, 0)        # bord à 27,5 mm : loin des lignes
    assert (r["score"], r["doute"], r["alternative"]) == (9, False, None)
    # Saisie à la main : jamais « à confirmer »
    assert bl.score_fleche(B40, 21.5, 0, detecte=False)["doute"] is False


def test_poulies_10_reduit():
    b = bl.Blason(diametre_mm=400, poulies=True)
    assert score(b, 7.5, 0) == "10"        # dans le petit cercle
    assert score(b, 15, 0) == "9"          # l'ancien 10 vaut 9
    assert bl.score_fleche(b, 0, 0)["x"] is False


def test_blason_reduit():
    b = bl.Blason(diametre_mm=800, zone_min=5)  # zones de 40 mm, imprimé jusqu'au 5
    assert score(b, 0, 230) == "5"
    assert score(b, 0, 250) == "M"


def test_trispot_vertical():
    b = bl.Blason(diametre_mm=400, zone_min=6, disposition="trispot_vertical", ecart_mm=220)
    r = bl.score_fleche(b, 3, 225)         # spot du haut, 5 mm au-dessus de son centre
    assert (r["spot"], r["score"], r["x"]) == (0, 10, True)
    assert (r["rel_x_mm"], r["rel_y_mm"]) == (3, 5)
    assert bl.score_fleche(b, 0, -300)["spot"] == 2
    hors = bl.score_fleche(b, 0, 110)      # entre deux spots, hors du 6
    assert (hors["score"], hors["spot"]) == (0, None)


def test_trispot_triangle_centres_equidistants():
    b = bl.Blason(disposition="trispot_triangle", ecart_mm=220)
    c = bl.centres(b)
    distances = {round(math.dist(c[i], c[j]), 6) for i in range(3) for j in range(i + 1, 3)}
    assert distances == {220.0}


def test_regle_du_trispot_une_fleche_par_spot():
    b = bl.Blason(diametre_mm=400, zone_min=6, disposition="trispot_vertical")
    impacts = []
    for x, y in [(0, 222), (25, 220), (0, 0)]:   # deux flèches dans le spot du haut
        r = bl.score_fleche(b, x, y)
        impacts.append(dict(r, score_auto=r["score"], x_auto=r["x"]))
    bl.appliquer_trispot(b, impacts)
    assert [(i["score"], i["double"]) for i in impacts] == [(0, True), (9, False), (10, False)]
    # Recalcul : la règle ne s'applique pas deux fois
    bl.appliquer_trispot(b, impacts)
    assert [(i["score"], i["double"]) for i in impacts] == [(0, True), (9, False), (10, False)]
    # Un score saisi à la main n'est jamais retiré : l'archer a tranché
    impacts[0]["manuel"] = True
    impacts[0]["score"], impacts[0]["x"] = 10, True
    bl.appliquer_trispot(b, impacts)
    assert [i["score"] for i in impacts] == [10, 9, 10]
