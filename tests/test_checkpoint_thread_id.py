from uuid import uuid4

import graph.graph as graph_module
from db.models.run import RunStatus
from graph.state import RunState


def test_run_graph_sets_thread_id_and_checkpointer(monkeypatch):
    captured: dict[str, object] = {}

    class FakeApp:
        def invoke(self, state, config):
            captured["config"] = config
            return state

    class FakeGraph:
        def compile(self, checkpointer=None):
            captured["checkpointer"] = checkpointer
            return FakeApp()

    monkeypatch.setattr(graph_module, "build_graph", lambda: FakeGraph())
    sentinel = object()
    monkeypatch.setattr(graph_module, "get_checkpointer", lambda: sentinel)

    state = RunState(run_id=uuid4(), intent="test", status=RunStatus.RUNNING)
    graph_module.run_graph(db=None, state=state)

    config = captured.get("config")
    assert config is not None
    assert config["configurable"]["thread_id"] == str(state.run_id)
    assert captured.get("checkpointer") is sentinel
