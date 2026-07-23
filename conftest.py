# Sa presence a la racine met le dossier projet sur sys.path,
# pour que `import kems` fonctionne depuis tests/.
import pytest

from kems.engine import rules

DECLENCHEUR = "le chat dort"


@pytest.fixture
def armer_signal():
    """Rend un KEMPS recevable : le porteur du carre emet le declencheur en public.

    Depuis le volet 1, un KEMPS est annule si le declencheur n'a jamais ete emis par le
    partenaire. Les tests qui veulent resoudre un appel doivent donc l'armer d'abord.
    """
    def _armer(state, equipe: int, porteur: int) -> None:
        rules.poser_signal(state, equipe, "notre convention", declencheur=DECLENCHEUR)
        rules._log(state, "MESSAGE", porteur,
                   f"{state.players[porteur].nom} : « tiens, {DECLENCHEUR} deja »")
    return _armer
