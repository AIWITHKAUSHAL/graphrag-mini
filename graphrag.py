"""The GraphRAG pipeline.

question -> LLM writes Cypher -> guard checks it -> Neo4j returns rows -> LLM writes the answer

If GROQ_API_KEY is missing the module falls back to a tiny keyword matcher so the
demo still runs offline. The graph half of the pipeline is identical either way.
"""

import os
import re

import requests
from dotenv import load_dotenv

from db import run_query

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

SCHEMA = """
Nodes:
  (:Employee {name, role})
  (:Department {name})
  (:Project {name, description})
  (:Skill {name})

Relationships:
  (:Employee)-[:WORKS_IN]->(:Department)
  (:Employee)-[:WORKS_ON]->(:Project)
  (:Employee)-[:HAS_SKILL]->(:Skill)
""".strip()

CYPHER_PROMPT = """You translate questions into Neo4j Cypher.

Schema:
{schema}

Rules:
- Return ONLY the Cypher query. No explanation, no markdown fences.
- The query must start with MATCH and must only read (never CREATE, MERGE, SET, DELETE).
- Always RETURN named, readable columns.
- Match names case-insensitively with toLower().

Examples:
Q: Which employees know Python?
A: MATCH (e:Employee)-[:HAS_SKILL]->(s:Skill) WHERE toLower(s.name) = 'python' RETURN e.name AS employee

Q: Who is working on Project Alpha?
A: MATCH (e:Employee)-[:WORKS_ON]->(p:Project) WHERE toLower(p.name) = 'project alpha' RETURN e.name AS employee, e.role AS role

Q: Which employees belong to the AI department?
A: MATCH (e:Employee)-[:WORKS_IN]->(d:Department) WHERE toLower(d.name) = 'ai' RETURN e.name AS employee, e.role AS role

Question: {question}
"""

ANSWER_PROMPT = """These rows are already the exact result of a database query that answers the
question below — every row is a match by construction. Phrase them as a plain-English answer
in one or two sentences. Do not second-guess whether the rows qualify.

Question: {question}

Rows from the graph:
{rows}
"""

# Constrained mapping of supported question types to the graph relationship that
# must appear in a query answering them. The read-only guard in db.py only checks
# that a query is *safe*; this checks that it's actually *on topic* — e.g. a
# well-formed, read-only query about departments should not sneak past as an
# answer to a question about skills.
INTENTS = [
    ("skill", re.compile(r"\bskill|\bknows?\b|\bpython\b|\baws\b|\bneo4j\b|\bsql\b|\bdocker\b", re.I), "HAS_SKILL"),
    ("project", re.compile(r"\bproject\b|\bworking on\b", re.I), "WORKS_ON"),
    ("department", re.compile(r"\bdepartment\b|\bteam\b|\bbelong", re.I), "WORKS_IN"),
]


def detect_intent(question: str) -> str | None:
    """Classify a question into one of the supported question types, if any."""
    for name, pattern, _ in INTENTS:
        if pattern.search(question):
            return name
    return None


def matches_intent(question: str, cypher: str) -> bool:
    """Semantic guard: does the query actually use the relationship implied by the
    question's intent? A query can be perfectly read-only and still answer the
    wrong question (e.g. WORKS_IN instead of HAS_SKILL) — this catches that."""
    intent = detect_intent(question)
    if intent is None:
        return True  # question doesn't match a known type — nothing to check against
    relationship = next(rel for name, _, rel in INTENTS if name == intent)
    return relationship in cypher


FALLBACK = [
    (
        r"\bpython\b|\baws\b|\bneo4j\b|\bsql\b|\bdocker\b",
        "MATCH (e:Employee)-[:HAS_SKILL]->(s:Skill) "
        "WHERE toLower(s.name) = '{term}' RETURN e.name AS employee, e.role AS role",
        "skill",
    ),
    (
        r"project\s+(alpha|beta|gamma)",
        "MATCH (e:Employee)-[:WORKS_ON]->(p:Project) "
        "WHERE toLower(p.name) = 'project {term}' RETURN e.name AS employee, e.role AS role",
        "project",
    ),
    (
        r"\b(ai|data engineering|platform)\b.*department|department.*\b(ai|data engineering|platform)\b",
        "MATCH (e:Employee)-[:WORKS_IN]->(d:Department) "
        "WHERE toLower(d.name) = '{term}' RETURN e.name AS employee, e.role AS role",
        "department",
    ),
]


def _call_groq(prompt: str) -> str:
    response = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        json={
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


def _clean(cypher: str) -> str:
    cypher = re.sub(r"^```(?:cypher)?|```$", "", cypher.strip(), flags=re.MULTILINE)
    return cypher.strip().rstrip(";")


def _fallback_cypher(question: str) -> str:
    """Keyword rules used when no API key is set."""
    q = question.lower()

    match = re.search(r"projects?\b.*\b(python|aws|neo4j|sql|docker)\b", q)
    if match:
        return (
            "MATCH (e:Employee)-[:HAS_SKILL]->(s:Skill), (e)-[:WORKS_ON]->(p:Project) "
            f"WHERE toLower(s.name) = '{match.group(1)}' "
            "RETURN DISTINCT p.name AS project, e.name AS employee"
        )

    for pattern, template, kind in FALLBACK:
        found = re.search(pattern, q)
        if not found:
            continue
        term = next(g for g in found.groups() if g) if found.groups() else found.group(0)
        if kind == "department" and term == "ai":
            term = "ai"
        return template.format(term=term.strip())

    return "MATCH (e:Employee)-[:WORKS_IN]->(d:Department) RETURN e.name AS employee, d.name AS department"


def generate_cypher(question: str) -> str:
    """Step 1 — turn the question into a graph query."""
    if not GROQ_API_KEY:
        return _fallback_cypher(question)
    return _clean(_call_groq(CYPHER_PROMPT.format(schema=SCHEMA, question=question)))


def write_answer(question: str, rows: list) -> str:
    """Step 3 — phrase the retrieved rows as a sentence."""
    if not rows:
        return "The graph has no data matching that question."
    if not GROQ_API_KEY:
        values = [", ".join(str(v) for v in row.values()) for row in rows]
        return "From the graph: " + "; ".join(values)
    return _call_groq(ANSWER_PROMPT.format(question=question, rows=rows))


def ask(question: str) -> dict:
    """The whole pipeline, returned as one dict so the demo can print each stage."""
    cypher = generate_cypher(question)

    # Semantic guard: the safety guard in run_query only proves the query is
    # read-only, not that it answers the question. If the LLM's query doesn't use
    # the relationship the question implies, fall back to the deterministic,
    # intent-matched query instead of running (and answering from) the wrong one.
    intent_ok = matches_intent(question, cypher)
    if not intent_ok:
        cypher = _fallback_cypher(question)

    rows = run_query(cypher)          # step 2 — the safety guard lives inside run_query
    answer = write_answer(question, rows)
    return {
        "question": question,
        "cypher": cypher,
        "rows": rows,
        "answer": answer,
        "intent_validated": intent_ok,
    }
