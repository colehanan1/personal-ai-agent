from agents.nexus import NEXUS
import pytest

pytestmark = pytest.mark.integration(reason="NEXUS initialization is slow; opt-in only.")


def test_route_request_tool_weather():
    nexus = NEXUS()
    decision = nexus.route_request("What's the weather tomorrow?")
    assert decision.route == "tool"
    assert decision.tool_name == "weather"


def test_route_request_tool_arxiv():
    nexus = NEXUS()
    decision = nexus.route_request("Find 3 papers on dopamine in Drosophila")
    assert decision.route == "tool"
    assert decision.tool_name == "arxiv"


def test_route_request_cortex():
    nexus = NEXUS()
    decision = nexus.route_request("Please implement a JSON parser.")
    assert decision.route == "cortex"


def test_route_request_frontier():
    nexus = NEXUS()
    decision = nexus.route_request("Research recent reinforcement learning trends.")
    assert decision.route == "frontier"


def test_route_request_default_nexus():
    nexus = NEXUS()
    decision = nexus.route_request("Summarize what you know about my current projects.")
    assert decision.route == "nexus"
