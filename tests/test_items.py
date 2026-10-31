import pytest

from game.items import Inventory, Item, ItemKind

KEY1, KEY2 = Item(ItemKind.KEYCARD, 1), Item(ItemKind.KEYCARD, 2)
DATA, DECOY = Item(ItemKind.DATA), Item(ItemKind.DECOY)


def test_add_count_and_stack():
    inv = Inventory()
    inv.add(DECOY)
    inv.add(DECOY, 2)
    assert inv.count(DECOY) == 3 and inv.count(DATA) == 0


def test_remove_decrements_and_deletes_empty_stacks():
    inv = Inventory()
    inv.add(DECOY, 2)
    assert inv.remove(DECOY)
    assert inv.count(DECOY) == 1
    assert inv.remove(DECOY)
    assert inv.stacks() == []


def test_remove_more_than_owned_changes_nothing():
    inv = Inventory()
    inv.add(DECOY)
    assert not inv.remove(DECOY, 2)
    assert inv.count(DECOY) == 1
    assert not inv.remove(DATA)


def test_add_rejects_non_positive_counts():
    with pytest.raises(ValueError):
        Inventory().add(DECOY, 0)


def test_keycard_levels():
    inv = Inventory()
    assert inv.has_keycard(0)  # niveau 0 : pas de badge nécessaire
    assert not inv.has_keycard(1)
    inv.add(KEY1)
    assert inv.has_keycard(1) and not inv.has_keycard(2)
    inv.add(KEY2)
    assert inv.has_keycard(2) and inv.has_keycard(1)  # un badge supérieur ouvre les portes inférieures


def test_higher_keycard_alone_opens_lower_doors():
    inv = Inventory()
    inv.add(KEY2)
    assert inv.has_keycard(1)


def test_data_is_not_a_keycard():
    inv = Inventory()
    inv.add(DATA)
    assert not inv.has_keycard(1)
    assert inv.count_kind(ItemKind.DATA) == 1 and inv.count_kind(ItemKind.KEYCARD) == 0


def test_stacks_have_a_stable_order():
    inv = Inventory()
    for item in (DECOY, KEY2, DATA, KEY1):
        inv.add(item)
    assert [i for i, _ in inv.stacks()] == [KEY1, KEY2, DATA, DECOY]


def test_labels():
    assert KEY2.label == "Badge niv. 2"
    assert DATA.label == "Données" and DECOY.label == "Leurre"
