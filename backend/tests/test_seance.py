from datetime import datetime, timedelta, timezone

import pytest

from app import seance
from app.config import Config

T0 = datetime(2026, 10, 23, 18, 0, 0, tzinfo=timezone.utc)


def config(**volees):
    return Config.model_validate({"volees": volees or {}, "cameras": []})


def test_fleches_numerotees_et_anti_rebond():
    c = config(fleches_par_volee=6, nouvelle_apres_s=90)
    e = seance.etat_initial(c, T0)
    f1 = seance.enregistrer_lacher(e, c, T0)
    assert f1["id"] == "V01_F1"
    assert seance.enregistrer_lacher(e, c, T0 + timedelta(seconds=1)) is None  # rebond
    f2 = seance.enregistrer_lacher(e, c, T0 + timedelta(seconds=30))
    assert f2["id"] == "V01_F2"
    assert f2["dossier"] == f"{e['seance']['id']}/volee01/fleche2"


def test_volee_pleine_ouvre_la_suivante():
    c = config(fleches_par_volee=3, nouvelle_apres_s=300)
    e = seance.etat_initial(c, T0)
    ids = [seance.enregistrer_lacher(e, c, T0 + timedelta(seconds=20 * i))["id"] for i in range(4)]
    assert ids == ["V01_F1", "V01_F2", "V01_F3", "V02_F1"]


def test_longue_pause_ouvre_une_volee():
    c = config(fleches_par_volee=6, nouvelle_apres_s=90)
    e = seance.etat_initial(c, T0)
    seance.enregistrer_lacher(e, c, T0)
    f = seance.enregistrer_lacher(e, c, T0 + timedelta(seconds=200))
    assert f["id"] == "V02_F1"


def test_nouvelle_volee_manuelle_ne_saute_pas_de_numero():
    c = config(fleches_par_volee=6, nouvelle_apres_s=90)
    e = seance.etat_initial(c, T0)
    seance.enregistrer_lacher(e, c, T0)
    assert seance.nouvelle_volee(e)
    assert not seance.nouvelle_volee(e)  # volée vide : pas de saut
    # Longue pause après le changement manuel : on reste en volée 2
    f = seance.enregistrer_lacher(e, c, T0 + timedelta(seconds=300))
    assert f["id"] == "V02_F1"


def test_impact_associe_a_la_plus_recente_sans_impact():
    c = config()
    e = seance.etat_initial(c, T0)
    f1 = seance.enregistrer_lacher(e, c, T0)
    f2 = seance.enregistrer_lacher(e, c, T0 + timedelta(seconds=20))
    f2["impact"] = {"score": 9}
    assert seance.fleche_pour_impact(e, None) is f1
    assert seance.fleche_pour_impact(e, "V01_F2") is f2


@pytest.mark.parametrize(
    "distance, score, est_x",
    [
        (0, 10, True),
        (30, 10, True),      # blason 122 cm : zone de 61 mm, X jusqu'à 30,5 mm
        (63, 10, False),     # touche la ligne du 10 : compte 10
        (64, 9, False),
        (600, 1, False),
        (700, 0, False),     # hors blason
    ],
)
def test_score_blason_122(distance, score, est_x):
    assert seance.score_wa(distance, 1220) == (score, est_x)


def test_csv():
    c = config()
    e = seance.etat_initial(c, T0)
    f = seance.enregistrer_lacher(e, c, T0)
    f["impact"] = {"score": 10, "x": True, "x_mm": 1.25, "y_mm": -3.0}
    lignes = seance.contenu_csv(e).splitlines()
    assert lignes[0].startswith("volee;fleche;heure;score")
    assert lignes[1].split(";")[:7] == ["1", "1", T0.astimezone().strftime("%H:%M:%S"), "10", "X", "1.2", "-3.0"]


def test_reconcilier_disposition():
    c = Config.model_validate({"cameras": [
        {"id": "a", "nom": "A", "type": "reseau"},
        {"id": "c", "nom": "C", "type": "reseau"},
    ]})
    e = {"disposition": {"ordre": ["b", "c", "a"], "masquees": ["b", "c"], "focus": "b"}}
    seance.reconcilier_disposition(e, c)
    assert e["disposition"] == {"ordre": ["c", "a"], "masquees": ["c"], "focus": None}


def test_id_seance_unique_meme_dans_la_meme_seconde():
    a = seance.nouvel_id_seance(T0)
    assert a == "2026-10-23_18h00m00"
    b = seance.nouvel_id_seance(T0, a)
    c = seance.nouvel_id_seance(T0, b)
    assert len({a, b, c}) == 3 and c == "2026-10-23_18h00m00-3"
    e = seance.etat_initial(config(), T0)
    ancien = e["seance"]["id"]
    seance.nouvelle_seance(e, T0)
    assert e["seance"]["id"] != ancien


def test_volees_a_archiver_attend_les_clips():
    c = config(fleches_par_volee=2, nouvelle_apres_s=300)
    e = seance.etat_initial(c, T0)
    for i in range(3):
        seance.enregistrer_lacher(e, c, T0 + timedelta(seconds=10 * i))
    assert seance.volees_a_archiver(e) == []  # clips de V1 pas encore prêts
    for f in e["fleches"]:
        f["statut"] = "pret"
    assert seance.volees_a_archiver(e) == [1]
    assert seance.volees_a_archiver(e, toutes=True) == [1, 2]
    e["rejeu"] = {"fleche_id": "V01_F2"}
    seance.marquer_archivee(e, 1)
    assert e["rejeu"] is None and e["fleches"][0]["archivee"]
    assert seance.volees_a_archiver(e) == []


def test_annuler_seulement_dans_la_volee_en_cours():
    c = config(fleches_par_volee=1, nouvelle_apres_s=300)
    e = seance.etat_initial(c, T0)
    seance.enregistrer_lacher(e, c, T0)
    assert seance.annuler_derniere(e)["id"] == "V01_F1"
    assert e["fleches"] == [] and e["fleche"] == 0
    assert seance.annuler_derniere(e) is None
    seance.enregistrer_lacher(e, c, T0 + timedelta(seconds=10))
    seance.nouvelle_volee(e)
    assert seance.annuler_derniere(e) is None  # volée en cours vide


def test_groupement():
    assert seance.groupement([{"x_mm": 0, "y_mm": 0}]) is None
    g = seance.groupement([{"x_mm": 0, "y_mm": 3}, {"x_mm": 0, "y_mm": -3}, {"x_mm": None, "y_mm": None}])
    assert g == {"n": 2, "centre_x_mm": 0.0, "centre_y_mm": 0.0, "dispersion_mm": 3.0}


def test_csv_groupements():
    c = config()
    e = seance.etat_initial(c, T0)
    for i, x in enumerate((0, 20)):
        f = seance.enregistrer_lacher(e, c, T0 + timedelta(seconds=10 * i))
        f["impact"] = {"x_mm": x, "y_mm": 0, "score": 10}
    lignes = seance.contenu_csv_groupements(e).splitlines()
    assert lignes[1] == "1;2;10.0;0.0;10.0"
    assert lignes[2] == "seance;2;10.0;0.0;10.0"
