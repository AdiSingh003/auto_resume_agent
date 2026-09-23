from backend.agents.graph import (
    agent_graph,
    continue_if_present,
    recursion_limit_for,
    should_revise_or_finalize,
)
from backend.models.schemas import EvaluationFeedback, EvaluationResult


def _evaluation(passed: bool, feedback=()):
    return EvaluationResult(
        ats_score=80,
        formatting_score=85,
        factual_consistency_score=95 if passed else 60,
        passed=passed,
        feedback=list(feedback),
    )


def test_passing_scores_finalize():
    assert should_revise_or_finalize({"evaluation": _evaluation(True), "revision_count": 0, "max_revisions": 3}) == "verify"


def test_low_scores_trigger_revision():
    assert should_revise_or_finalize({"evaluation": _evaluation(False), "revision_count": 1, "max_revisions": 3}) == "revise"


def test_critical_factual_issue_triggers_revision():
    feedback = [EvaluationFeedback(category="factual", severity="critical", issue="Invented metric")]
    state = {"evaluation": _evaluation(False, feedback), "revision_count": 0, "max_revisions": 3}
    assert should_revise_or_finalize(state) == "revise"


def test_revision_limit_forces_finalize():
    assert should_revise_or_finalize({"evaluation": _evaluation(False), "revision_count": 3, "max_revisions": 3}) == "verify"


def test_missing_evaluation_finalizes():
    assert should_revise_or_finalize({"evaluation": None, "revision_count": 0, "max_revisions": 3}) == "verify"


def test_continue_if_present_aborts_when_prerequisite_missing():
    route = continue_if_present("parsed_jd", "research_role")
    assert route({"parsed_jd": None}) == "abort"
    assert route({"parsed_jd": object()}) == "research_role"


def test_graph_contains_replanning_cycle():
    edges = {(edge.source, edge.target) for edge in agent_graph.get_graph().edges}
    assert ("evaluate", "revise") in edges
    assert ("revise", "draft_resume") in edges
    assert ("evaluate", "verify") in edges
    assert ("verify", "report") in edges


def test_recursion_limit_covers_every_revision_cycle():
    for max_revisions in range(6):
        steps_needed = 4 + 3 * (max_revisions + 1) + max_revisions + 2
        assert recursion_limit_for(max_revisions) > steps_needed
