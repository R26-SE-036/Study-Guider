from neo4j import GraphDatabase
from app.core.config import settings

class Neo4jConnection:
    def __init__(self):
        self.driver = None
        self.connect()

    def connect(self):
        """Creates a new connection to Neo4j with connection pooling."""
        try:
            self.driver = GraphDatabase.driver(
                settings.NEO4J_URI, 
                auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD),
                max_connection_lifetime=200 
            )
            self.driver.verify_connectivity()
            print("\n" + "="*40)
            print("🟢 NEO4J GRAPH DATABASE CONNECTED SUCCESSFULLY!")
            print("="*40 + "\n")
        except Exception as e:
            print(f"\n❌ Neo4j Connection Failed: {e}\n")
            self.driver = None

    def close(self):
        if self.driver:
            self.driver.close()

    def execute_query(self, query, parameters=None):
        """Executes a query with Auto-Reconnect logic if the connection drops."""
        if not self.driver:
            print("⚠️ No database connection. Attempting to reconnect...")
            self.connect()
            
        if not self.driver:
            return None
            
        try:
            with self.driver.session() as session:
                result = session.run(query, parameters)
                return [record.data() for record in result]
        except Exception as e:
            print(f"⚠️ Neo4j query failed. Reconnecting... Error: {e}")
            self.connect()
            if self.driver:
                try:
                    with self.driver.session() as session:
                        result = session.run(query, parameters)
                        return [record.data() for record in result]
                except Exception as retry_error:
                    print(f"❌ Neo4j query retry failed: {retry_error}")
            return None

# Global instance
neo4j_db = Neo4jConnection()