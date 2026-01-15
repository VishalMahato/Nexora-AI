from types import SimpleNamespace

from graph.utils.routing import route_post_step


def _state_with_artifacts(artifacts: dict):
    return SimpleNamespace(artifacts=artifacts)


def test_route_post_step_fatal_error_wins():
    state = _state_with_artifacts({"fatal_error": {"message": "boom"}, "needs_input": {"missing": ["x"]}})
    assert route_post_step(state, default_next="PLAN_TX") == "FINALIZE"


def test_route_post_step_needs_input_routes_to_clarify():
    state = _state_with_artifacts({"needs_input": {"missing": ["wallet_address"]}})
    assert route_post_step(state, default_next="PLAN_TX") == "CLARIFY"


def test_route_post_step_defaults_to_next():
    state = _state_with_artifacts({})
    assert route_post_step(state, default_next="PLAN_TX") == "PLAN_TX"
