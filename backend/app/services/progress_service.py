from app.db.neo4j_connection import neo4j_db
from datetime import datetime

def update_student_progress(student_id: str, concept: str, score: int, total: int):
    """
    Saves a new Quiz Attempt node for the student to maintain a history of their progress,
    instead of overwriting the previous score.
    """
    percentage = (score / total) * 100 if total > 0 else 0
    status = "MASTERED" if percentage >= 50 else "NEEDS_REVIEW"
    timestamp = datetime.now().isoformat()

    query = """
    MERGE (s:Student {student_id: $student_id})
    MERGE (c:Concept {name: $concept})
    CREATE (s)-[a:ATTEMPTED {
        score: $score,
        total: $total,
        percentage: $percentage,
        status: $status,
        timestamp: $timestamp
    }]->(c)
    RETURN a
    """
    
    parameters = {
        "student_id": student_id,
        "concept": concept,
        "score": score,
        "total": total,
        "percentage": percentage,
        "status": status,
        "timestamp": timestamp
    }
    
    try:
        result = neo4j_db.execute_query(query, parameters)
        return {"success": True, "data": result}
    except Exception as e:
        print(f"❌ Progress Update Error: {e}")
        return {"success": False, "error": str(e)}

def get_student_progress(student_id: str):
    """Retrieves all past attempts for the dashboard timeline."""
    query = """
    MATCH (s:Student {student_id: $student_id})-[a:ATTEMPTED]->(c:Concept)
    RETURN c.name AS concept, a.score AS score, a.total AS total, 
           a.percentage AS percentage, a.status AS status, a.timestamp AS last_updated
    ORDER BY a.timestamp DESC
    """
    try:
        result = neo4j_db.execute_query(query, {"student_id": student_id})
        return {"success": True, "data": result}
    except Exception as e:
        print(f"❌ Progress Fetch Error: {e}")
        return {"success": False, "error": str(e)}