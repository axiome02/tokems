from kems.engine.cards import SUITS, Card, build_deck, is_square, square_rank


def test_deck_size():
    assert len(build_deck(10)) == 40
    assert len(build_deck(13)) == 52
    assert len(set(build_deck(10))) == 40  # all unique


def test_square():
    hand = [Card(7, c) for c in SUITS]
    assert is_square(hand)
    assert square_rank(hand) == 7


def test_not_square():
    hand = [Card(7, "♠"), Card(7, "♥"), Card(7, "♦"), Card(8, "♣")]
    assert not is_square(hand)
    assert square_rank(hand) is None
