import numpy as np

from detecteur import Detecteur, niveau_dbfs


def test_niveau():
    assert niveau_dbfs(np.array([0.5, -1.0], np.float32)) == 0.0
    assert round(niveau_dbfs(np.array([0.1], np.float32))) == -20
    assert niveau_dbfs(np.zeros(10, np.float32)) < -100


def test_seuil_et_anti_rebond():
    d = Detecteur(seuil_db=-20, anti_rebond_s=2)
    assert not d.bloc(-30, 0.0)       # trop faible
    assert d.bloc(-10, 1.0)           # lâcher
    assert not d.bloc(-5, 1.5)        # écho / vibration
    assert d.bloc(-10, 3.2)           # flèche suivante
