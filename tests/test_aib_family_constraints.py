import pytest

from scripts.build_aib_family_constraints import components


def test_transitive_links_are_order_independent_and_keep_singletons():
    groups = [["a", "b"], ["c", "b"]]
    expected = [["a", "b", "c"], ["d"]]
    assert components(["d", "b", "a", "c"], groups) == expected
    assert components(["a", "b", "c", "d"], list(reversed(groups))) == expected


@pytest.mark.parametrize("ids,groups", [(["a", "a"], []), (["a"], [["b"]]), (["a"], [[]])])
def test_invalid_identity_is_rejected(ids, groups):
    with pytest.raises(ValueError):
        components(ids, groups)
