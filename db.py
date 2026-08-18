"""Neo4j connection + read-only query execution."""

import os
import re

from dotenv import load_dotenv
from neo4j import GraphDatabase, exceptions as neo4j_exceptions

load_dotenv()

URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
USER = os.getenv("NEO4J_USER", "neo4j")
PASSWORD = os.getenv("NEO4J_PASSWORD", "password123")

WRITE_CLAUSES = re.compile(
    r"\b(create|merge|delete|detach|set|remove|drop|load\s+csv|call\s*\{)\b", re.IGNORECASE
)

_driver = None


def get_driver():
    global _driver
    if _driver is None:
        try:
            _driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
            # verify connectivity now so we surface helpful errors early
            _driver.verify_connectivity()
        except neo4j_exceptions.ServiceUnavailable as error:
            hint = (
                f"Unable to connect to Neo4j at {URI}: {error}\n"
                "Ensure Neo4j is running and reachable on that host/port.\n"
                "If you're using Docker, start Docker Desktop and run a Neo4j container,\n"
                "or set environment variables (NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD) to a reachable DB.\n"
                "You can create a .env file in the project root with those values."
            )
            raise RuntimeError(hint) from error
    return _driver


def is_read_only(cypher: str) -> bool:
    """Guard: the generated query must only read. Two things must hold —
    it starts with MATCH, and it contains no write clause anywhere."""
    stripped = cypher.strip()
    if not stripped.upper().startswith("MATCH"):
        return False
    return WRITE_CLAUSES.search(stripped) is None


def run_query(cypher: str, limit: int = 25):
    """Execute a validated read-only query and return a list of dicts."""
    if not is_read_only(cypher):
        raise ValueError(f"Blocked unsafe query: {cypher}")

    driver = get_driver()
    with driver.session(default_access_mode="READ") as session:
        return [record.data() for record in session.run(cypher)][:limit]
