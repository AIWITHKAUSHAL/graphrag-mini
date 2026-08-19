"""Tests for the four required demo questions (see app.py QUESTIONS).

Two layers:
- Unit tests (default, no DB needed): mock db.run_query and drive the pipeline
  end to end, checking Cypher generation, the semantic intent guard, and the
  phrased answer.
- An integration test that runs against a real, freshly-seeded Neo4j instance.
  It's opt-in (set RUN_INTEGRATION_TESTS=1) and skips automatically if Neo4j
  isn't reachable, since it rebuilds the graph via seed.py and shouldn't run
  against a database anyone cares about by accident.

Both layers force the offline keyword fallback (GROQ_API_KEY unset) so the
tests are deterministic and don't require network access or an API key.
"""

import os

import pytest

import graphrag


QUESTIONS = [
    "Which employees know Python?",
    "Who is working on Project Alpha?",
    "Which employees belong to the AI department?",
    "Which projects have employees with AWS skills?",
]

# Expected rows, computed by hand from the seed.py graph (5 employees, 3
# departments, 3 projects, 5 skills — see seed.py's EMPLOYEES/HAS_SKILL/WORKS_ON).
EXPECTED_ROWS = {
    QUESTIONS[0]: [
        {"employee": "Priya Sharma", "role": "ML Engineer"},
        {"employee": "Sneha Iyer", "role": "Data Scientist"},
        {"employee": "Rahul Verma", "role": "Data Engineer"},
    ],
    QUESTIONS[1]: [
        {"employee": "Priya Sharma", "role": "ML Engineer"},
        {"employee": "Sneha Iyer", "role": "Data Scientist"},
        {"employee": "Arjun Mehta", "role": "DevOps Engineer"},
    ],
    QUESTIONS[2]: [
        {"employee": "Priya Sharma", "role": "ML Engineer"},
        {"employee": "Sneha Iyer", "role": "Data Scientist"},
    ],
    QUESTIONS[3]: [
        {"project": "Project Beta", "employee": "Kavya Nair"},
        {"project": "Project Gamma", "employee": "Arjun Mehta"},
        {"project": "Project Alpha", "employee": "Arjun Mehta"},
    ],
}

# The relationship each question's Cypher must contain — mirrors graphrag.INTENTS.
EXPECTED_RELATIONSHIP = {
    QUESTIONS[0]: "HAS_SKILL",
    QUESTIONS[1]: "WORKS_ON",
    QUESTIONS[2]: "WORKS_IN",
    QUESTIONS[3]: "HAS_SKILL",  # joins HAS_SKILL + WORKS_ON; HAS_SKILL is what the intent checks
}


@pytest.fixture(autouse=True)
def offline_mode(monkeypatch):
    """Force the keyword fallback so no network/API key is needed."""
    monkeypatch.setattr(graphrag, "GROQ_API_KEY", "")


@pytest.mark.parametrize("question", QUESTIONS)
def test_generated_cypher_matches_question_intent(question):
    """The semantic guard: generated Cypher must use the relationship the
    question actually implies, not just be read-only."""
    cypher = graphrag.generate_cypher(question)
    assert EXPECTED_RELATIONSHIP[question] in cypher
    assert graphrag.matches_intent(question, cypher)


@pytest.mark.parametrize("question", QUESTIONS)
def test_ask_end_to_end_with_mocked_rows(monkeypatch, question):
    """Full pipeline with run_query mocked to return the known-correct rows for
    each question, verifying ask() wires cypher -> rows -> answer correctly and
    marks the query as intent-validated."""
    expected_rows = EXPECTED_ROWS[question]
    monkeypatch.setattr(graphrag, "run_query", lambda cypher: expected_rows)

    result = graphrag.ask(question)

    assert result["rows"] == expected_rows
    assert result["intent_validated"] is True
    for row in expected_rows:
        for value in row.values():
            assert str(value) in result["answer"]


def test_semantic_guard_rejects_off_topic_query(monkeypatch):
    """If the LLM (or a bug) produces a safe-but-wrong query — e.g. a department
    query for a skill question — ask() must not run it as-is. It should fall
    back to the deterministic, intent-matched query instead."""
    question = "Which employees know Python?"
    off_topic_cypher = (
        "MATCH (e:Employee)-[:WORKS_IN]->(d:Department) "
        "RETURN e.name AS employee, d.name AS department"
    )
    monkeypatch.setattr(graphrag, "generate_cypher", lambda q: off_topic_cypher)

    seen_queries = []

    def fake_run_query(cypher):
        seen_queries.append(cypher)
        return EXPECTED_ROWS[question]

    monkeypatch.setattr(graphrag, "run_query", fake_run_query)

    result = graphrag.ask(question)

    assert result["intent_validated"] is False
    assert result["cypher"] != off_topic_cypher
    assert "HAS_SKILL" in result["cypher"]
    assert seen_queries == [result["cypher"]]  # the off-topic query was never run


def test_unrecognized_question_skips_the_guard():
    """Questions outside the four supported types have no intent to validate
    against — matches_intent should let them through rather than block them."""
    assert graphrag.detect_intent("How many nodes are in the graph?") is None
    assert graphrag.matches_intent("How many nodes are in the graph?", "MATCH (n) RETURN count(n)")


@pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "1",
    reason="opt-in: set RUN_INTEGRATION_TESTS=1 to run against a real Neo4j instance",
)
class TestAgainstSeededDatabase:
    """End-to-end tests against a real Neo4j instance, seeded fresh via seed.py.

    Opt-in and skipped by default because it wipes and rebuilds whatever
    database NEO4J_URI points at — point .env at a disposable test instance
    before setting RUN_INTEGRATION_TESTS=1.
    """

    @pytest.fixture(autouse=True, scope="class")
    def seeded_graph(self):
        import db
        import seed

        try:
            db.get_driver()
        except RuntimeError as error:
            pytest.skip(f"Neo4j not reachable: {error}")

        seed.main()
        yield

    @pytest.mark.parametrize("question", QUESTIONS)
    def test_expected_rows_from_real_db(self, question):
        result = graphrag.ask(question)
        assert result["intent_validated"] is True

        actual = {tuple(sorted(row.items())) for row in result["rows"]}
        expected = {tuple(sorted(row.items())) for row in EXPECTED_ROWS[question]}
        assert actual == expected
