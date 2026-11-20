from config import MODEL_ID
from pebble_support.agent import root_agent


def test_agent_wiring():
    assert root_agent.name == "pebble_support"
    assert root_agent.model.model == MODEL_ID
    assert root_agent.model.retry_options.attempts == 2
    assert [t.__name__ for t in root_agent.tools] == ["lookup_order", "refund_order"]
