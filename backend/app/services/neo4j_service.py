import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

# Load environment variables
base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
env_path = os.path.join(base_dir, '.env')
load_dotenv(env_path)

uri = os.getenv("NEO4J_URI")
user = os.getenv("NEO4J_USERNAME")
password = os.getenv("NEO4J_PASSWORD")

class Neo4jConnection:
    def __init__(self):
        self.driver = None
        self.connect()

    def connect(self):
        """Creates a new connection to Neo4j with connection pooling to prevent SSLEOFError"""
        try:
            # FIX: Added max_connection_lifetime=200s to avoid AuraDB idle timeouts
            self.driver = GraphDatabase.driver(
                uri, 
                auth=(user, password),
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
        """Executes a query with Auto-Reconnect logic if the connection was dropped"""
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
            # FIX: If SSLEOFError occurs during query, reconnect and try exactly once more
            print(f"⚠️ Neo4j query failed (Connection lost). Reconnecting... Error: {e}")
            self.connect()
            if self.driver:
                try:
                    with self.driver.session() as session:
                        result = session.run(query, parameters)
                        return [record.data() for record in result]
                except Exception as retry_error:
                    print(f"❌ Neo4j query retry failed: {retry_error}")
            return None

# Create a global instance to be used across the app
neo4j_db = Neo4jConnection()