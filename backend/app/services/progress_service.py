from app.db.neo4j_connection import neo4j_db
from datetime import datetime

def update_student_progress(student_id: str, concept: str, score: int, total: int):
    # Determine mastery status based on score
    if score >= (total / 2):
        relationship = "MASTERED" 
    else:
        relationship = "NEEDS_REVIEW" 
        
    # Cypher query to create or update the graph relationship
    query = f"""
    MERGE (s:Student {{id: $student_id}})
    MERGE (c:Concept {{name: $concept}})
    MERGE (s)-[r:{relationship}]->(c)
    SET r.latest_score = $score, 
        r.total_questions = $total, 
        r.last_updated = $time
    RETURN s.id AS student, type(r) AS status, c.name AS concept
    """
    
    parameters = {
        "student_id": student_id,
        "concept": concept,
        "score": score,
        "total": total,
        "time": str(datetime.now())
    }
    
    try:
        result = neo4j_db.execute_query(query, parameters)
        return {"success": True, "message": "Graph updated successfully!", "data": result}
    except Exception as e:
        print(f"❌ Database Error: {e}")
        return {"success": False, "error": str(e)}

def get_student_progress(student_id: str):
    # Cypher query to fetch all concepts the student has interacted with
    query = """
    MATCH (s:Student {id: $student_id})-[r]->(c:Concept)
    RETURN c.name AS concept, type(r) AS status, r.latest_score AS score, r.total_questions AS total, r.last_updated AS last_updated
    ORDER BY r.last_updated DESC
    """
    
    parameters = {"student_id": student_id}
    
    try:
        results = neo4j_db.execute_query(query, parameters)
        return {"success": True, "data": results}
    except Exception as e:
        print(f"❌ Fetch Error: {e}")
        return {"success": False, "error": str(e)}