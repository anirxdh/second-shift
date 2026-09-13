import pytest

from evals.scenarios import SCENARIOS


@pytest.mark.parametrize("name,group,proves,fn", SCENARIOS, ids=[s[0] for s in SCENARIOS])
def test_scenario(name, group, proves, fn):
    passed, facts = fn()
    assert passed, "\n".join(facts)
