# graphrag-mini

A small GraphRAG system over an org graph — Employees, Departments, Projects, Skills.
Ask a question in plain English, an LLM turns it into Cypher, Neo4j answers it, the LLM
phrases the result. Five files, no framework.

```
question -> LLM writes Cypher -> read-only guard -> Neo4j -> rows -> LLM writes the answer
```

## Files

| File | What it does |
|---|---|
| `db.py` | Neo4j connection + the read-only guard |
| `seed.py` | Builds the demo graph (run once) |
| `graphrag.py` | The pipeline: question → Cypher → rows → answer |
| `app.py` | CLI demo, prints every stage |
| `.env.example` | Copy to `.env` and fill in |

## Setup

**1. Start Neo4j** (Docker is the fastest route):

```bash
docker run -d --name neo4j-demo -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password123 neo4j:5.26
```

Browser opens at http://localhost:7474 — log in with `neo4j` / `password123`.
Neo4j Desktop or a free Aura instance work equally well; just update `.env`.

**2. Install and configure:**

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows PowerShell
pip install -r requirements.txt
copy .env.example .env          # then edit it
```

A Groq key is optional. Without one, `graphrag.py` uses a keyword matcher to build the
Cypher so the demo still runs — the graph half of the pipeline is unchanged either way.
Get a free key at console.groq.com and paste it into `.env` for the real thing.

**3. Build the graph:**

```bash
python seed.py
```

**4. Run the demo:**

```bash
python app.py            # the four required questions
python app.py --chat     # ask your own
```

Each question prints `QUESTION → CYPHER → ROWS → ANSWER`, which is exactly the sequence
to narrate on camera.

## The graph

```
(:Employee)-[:WORKS_IN]->(:Department)
(:Employee)-[:WORKS_ON]->(:Project)
(:Employee)-[:HAS_SKILL]->(:Skill)
```

5 employees, 3 departments, 3 projects, 5 skills. Paste this into Neo4j Browser to see it:

```cypher
MATCH (n)-[r]->(m) RETURN n, r, m
```

## Recording checklist

1. Neo4j Browser — run the query above, show the nodes and arrows.
2. `python app.py` — show all four questions answering.
3. Open `graphrag.py`, point at `generate_cypher`, `run_query`, `write_answer` — the three
   stages, in order.
4. Show `is_read_only` in `db.py` blocking a `DELETE`, then explain why generated Cypher
   must never be trusted directly.
5. Close on the AWS question: vector search would have to find one document mentioning both
   AWS and a project name. The graph just walks `Skill ← HAS_SKILL ← Employee → WORKS_ON → Project`.

## Concepts covered

- **RAG** — retrieve real data first, then let the model phrase the answer, so it can't invent facts.
- **GraphRAG** — the retrieval step is a graph traversal instead of a similarity search over text chunks.
- **Why a graph** — questions that need to join two facts ("projects staffed by AWS people") are one
  traversal in a graph and a guess in a vector store, because no single chunk contains both facts.
- **Nodes** — the entities: Employee, Department, Project, Skill.
- **Relationships** — the typed, directed edges between them.
- **Properties** — key/value pairs stored on nodes, e.g. `name`, `role`, `description`.
- **Retrieval** — the LLM sees the schema, writes Cypher, the guard validates it, Neo4j executes it.
- **Reaching the LLM** — returned rows are pasted into a second prompt as the only allowed source
  for the final answer.

## Known limitation

The guard checks that a generated query is *safe* and *runs* — nothing verifies that it answers
the question actually asked. Worth stating out loud in the video.
