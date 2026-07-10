import json
import requests
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from app.services.rag_service import retrieve_context
from app.services.ml_service import predict_cognitive_state
from app.core.config import settings

try:
    # Initialize the language model using central settings
    llm = ChatGoogleGenerativeAI(
        model=settings.MODEL_NAME, 
        temperature=0.3, 
        google_api_key=settings.GEMINI_API_KEY,
        max_retries=0, 
        timeout=10 
    )
except Exception as e:
    llm = None

def get_smart_fallback(student_id, error_type, code_snippet):
    return {
        "issue": f"Logical Issue Detected: {error_type}",
        "explanation": f"Hello {student_id}, we noticed a struggle with {error_type}. Ensure you are using the correct syntax and logic.",
        "exampleCode": f"// Your Code:\n// {code_snippet}\n\n// Tip: Double check your operators and boundaries.",
        "mermaidDiagram": "graph TD\n    A[Code Execution] --> B{Check Condition}\n    B -- Invalid --> C[Logical Error]\n    B -- Valid --> D[Success]\n    style C fill:#FF453A,stroke:#333",
        "videoUrl": f"https://www.youtube.com/results?search_query=java+{error_type.replace('_', '+')}",
        "referenceLink": "https://docs.oracle.com/javase/tutorial/java/nutsandbolts/",
        "hint": "Check your logic boundaries and operators."
    }

def generate_real_lesson(student_id: str, error_type: str, code_snippet: str):
    if not settings.GEMINI_API_KEY:
        return get_smart_fallback(student_id, error_type, code_snippet)

    # --- DYNAMIC METRICS ---
    if "LOOP" in error_type:
        error_count = 6
        past_score = 30
    elif "ARRAY" in error_type:
        error_count = 4
        past_score = 60
    else:
        error_count = 3
        past_score = 80

    search_query = f"Explain {error_type} and how to fix {code_snippet}"
    retrieved_context = retrieve_context(search_query)

    cognitive_state = predict_cognitive_state(error_count, code_snippet, past_score)
    print(f"🎯 Guiding AI based on ML Prediction: {cognitive_state}")

    prompt_template = """
    You are 'Code Guru', an expert computer science tutor for first-year IT students.
    
    CRITICAL: You MUST focus ONLY on this specific error: "{error_type}"
    Student's Code: "{code_snippet}"

    === MACHINE LEARNING COGNITIVE ANALYSIS ===
    Predicted Student Cognitive State: "{cognitive_state}"
    INSTRUCTION: If the state is "High Cognitive Load" or "Needs Simple Basics", explain it extremely simply, step-by-step. If "Minor Syntax Error", give a quick direct correction.

    === SYLLABUS NOTES (Use ONLY as background context) ===
    {context}
    ======================

    Generate a micro-lesson specifically addressing the "{error_type}". 
    Do NOT give a generic lesson. It must be specific to the code provided.
    Also, generate a simple 'Mermaid.js' chart (graph TD) showing the visual breakdown of THIS specific error.
    
    Provide the response EXACTLY in this JSON format:
    {{
        "issue": "A specific 1-sentence title about {error_type}",
        "explanation": "A pedagogical explanation adapted to the ML Cognitive State and the specific error.",
        "exampleCode": "Show the student's incorrect code as a comment, and the correct way underneath.",
        "mermaidDiagram": "graph TD\\n A[Step 1] --> B[Step 2]",
        "videoUrl": "Provide YouTube URL relevant to {error_type}",
        "referenceLink": "Provide Documentation link relevant to {error_type}",
        "hint": "A guiding question specific to {error_type}"
    }}
    """

    prompt = PromptTemplate(input_variables=["student_id", "error_type", "code_snippet", "cognitive_state", "context"], template=prompt_template)
    
    formatted_prompt = prompt.format(
        student_id=student_id, 
        error_type=error_type, 
        code_snippet=code_snippet, 
        cognitive_state=cognitive_state,
        context=retrieved_context
    )
    
    content = ""

    try:
        response = llm.invoke(formatted_prompt)
        content = response.content
        print("✅ Graph RAG + ML Customization Success: Using LangChain")
    except Exception as e:
        print(f"\n⚠️ LangChain Failed: {e}. Switching to Smart Fallback API...")
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.MODEL_NAME}:generateContent?key={settings.GEMINI_API_KEY}"
            data = {"contents": [{"parts": [{"text": formatted_prompt}]}], "generationConfig": {"temperature": 0.3}}
            res = requests.post(url, headers={'Content-Type': 'application/json'}, json=data, timeout=10)
            if res.status_code == 200:
                content = res.json()['candidates'][0]['content']['parts'][0]['text']
            else:
                raise Exception(f"API Error {res.status_code}")
        except Exception as fallback_error:
            print(f"⚠️ Fallback API Failed: {fallback_error}. Serving Mock Data.")
            return get_smart_fallback(student_id, error_type, code_snippet)

    print(f"\n--- RAW AI LESSON OUTPUT ---\n{str(content)[:500]}...\n----------------------------\n")

    if isinstance(content, list) and len(content) > 0 and isinstance(content[0], dict) and 'text' in content[0]:
        content = content[0]['text']

    try:
        if isinstance(content, dict):
            return content
        elif isinstance(content, str):
            content = content.replace("```json", "").replace("```", "").strip()
            start_index = content.find('{')
            end_index = content.rfind('}')
            if start_index != -1 and end_index != -1:
                clean_json = content[start_index:end_index+1].replace("\\n", "\\\\n")
                return json.loads(clean_json)
        return get_smart_fallback(student_id, error_type, code_snippet)
    except Exception as parse_error:
        print(f"❌ JSON Parsing Error: {parse_error}")
        return get_smart_fallback(student_id, error_type, code_snippet)