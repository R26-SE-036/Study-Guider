"""The one connection to Neo4j, and what it does when Neo4j is not there.

============================ WHY IT RAISES NOW ============================
execute_query used to catch every failure, print it and return None, and every
caller read None as "no rows". So while the database was unreachable, saving a
quiz result answered {"success": True} with nothing written - the quiz page said
"Progress saved." - the progress page showed an empty history, the curriculum
showed every concept as untouched, and the lesson prompt told the model the
student had never attempted the concept. All of it with a 200.

It now raises GraphUnavailable when the database cannot be reached, and main.py
turns that into a 503 with a plain message. Only connection failures are
reported that way: a query the server rejects is a bug, and it is raised as the
Neo4j error it is rather than disguised as an outage.

============================ WHY IT WAITS ============================
One request can need several queries - a lesson reads the cache, the student's
mastery, their prerequisites and the syllabus. Reconnecting before each of them
against a host that is not answering made one lesson wait through every attempt
in turn. After a failed connection this refuses at once for RETRY_AFTER_SECONDS,
then tries again; the health check is what usually makes that attempt.
==========================================================================
"""

import time

from neo4j import GraphDatabase
from neo4j.exceptions import (
    DatabaseUnavailable,
    ServiceUnavailable,
    SessionExpired,
    TransientError,
)

from app.core.config import settings

# "The database could not be reached", as opposed to "the database refused this
# query". OSError covers the SSLEOFError Aura produces when it drops an idle
# connection, which is what the old catch-everything was written for.
CONNECTIVITY_ERRORS = (
    ServiceUnavailable,
    SessionExpired,
    DatabaseUnavailable,
    TransientError,
    OSError,
)

RETRY_AFTER_SECONDS = 30
CONNECTION_TIMEOUT_SECONDS = 5


class GraphUnavailable(RuntimeError):
    """The graph database could not be reached. Nothing was read or written."""


class Neo4jConnection:
    def __init__(self):
        self.driver = None
        self._retry_after = 0.0
        if not self.connect():
            self._retry_after = time.monotonic() + RETRY_AFTER_SECONDS

    def connect(self) -> bool:
        """Open a connection, replacing any existing one. False if it failed."""
        self.close()
        if not settings.NEO4J_URI:
            return False
        try:
            self.driver = GraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD),
                max_connection_lifetime=200,
                connection_timeout=CONNECTION_TIMEOUT_SECONDS,
            )
            self.driver.verify_connectivity()
            print("\n" + "=" * 40)
            print("🟢 NEO4J GRAPH DATABASE CONNECTED SUCCESSFULLY!")
            print("=" * 40 + "\n")
            return True
        except Exception as e:
            print(f"\n❌ Neo4j Connection Failed: {e}\n")
            self.close()
            return False

    def close(self):
        """Safely closes the Neo4j connection."""
        if self.driver:
            try:
                self.driver.close()
            except Exception:
                pass
            self.driver = None

    def reconnect_if_due(self) -> bool:
        """Connected, or reconnected now that the wait is over. False otherwise."""
        if self.driver:
            return True
        if time.monotonic() < self._retry_after:
            return False
        if self.connect():
            self._retry_after = 0.0
            return True
        self._retry_after = time.monotonic() + RETRY_AFTER_SECONDS
        return False

    def execute_query(self, query, parameters=None) -> list[dict]:
        """Run a query and return its rows: a list, empty when there are none.

        Raises GraphUnavailable when the database cannot be reached, after one
        reconnect for a connection that has gone stale. Any other failure is
        raised as it is.
        """
        if not self.reconnect_if_due():
            raise GraphUnavailable("The graph database could not be reached.")

        try:
            return self._run(query, parameters)
        except CONNECTIVITY_ERRORS as first_error:
            print(f"⚠️ Neo4j connection dropped; reconnecting once. Error: {first_error}")
            if not self.connect():
                self._retry_after = time.monotonic() + RETRY_AFTER_SECONDS
                raise GraphUnavailable("The graph database could not be reached.") from first_error
            try:
                return self._run(query, parameters)
            except CONNECTIVITY_ERRORS as retry_error:
                self.close()
                self._retry_after = time.monotonic() + RETRY_AFTER_SECONDS
                raise GraphUnavailable("The graph database could not be reached.") from retry_error

    def _run(self, query, parameters) -> list[dict]:
        with self.driver.session(database=settings.NEO4J_DATABASE) as session:
            result = session.run(query, parameters)
            return [record.data() for record in result]


# Global instance
neo4j_db = Neo4jConnection()
