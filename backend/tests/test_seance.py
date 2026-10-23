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
