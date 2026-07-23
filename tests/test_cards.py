from kems.engine.cards import COULEURS, Card, construire_paquet, est_carre, rang_du_carre


def test_paquet_taille():
    assert len(construire_paquet(10)) == 40
    assert len(construire_paquet(13)) == 52
    assert len(set(construire_paquet(10))) == 40  # toutes uniques


def test_carre():
    main = [Card(7, c) for c in COULEURS]
    assert est_carre(main)
    assert rang_du_carre(main) == 7


def test_pas_carre():
    main = [Card(7, "♠"), Card(7, "♥"), Card(7, "♦"), Card(8, "♣")]
    assert not est_carre(main)
    assert rang_du_carre(main) is None
