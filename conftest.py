# Its presence at root puts the project folder in sys.path,
# so `import kems` works from tests/.
import pytest

from kems.engine import rules

DECLENCHEUR = "the cat is sleeping"


@pytest.fixture
def armer_signal():
    """Makes a KEMPS call receivable: the square holder emits the trigger in public."""
    def _armer(state, team: int, porteur: int) -> None:
        rules.set_signal(state, team, "our convention", trigger=DECLENCHEUR)
        rules._log(state, "MESSAGE", porteur,
                   f"{state.players[porteur].name} : \"hey, {DECLENCHEUR} already\"")
    return _armer
