import json
import requests
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from app.core.config import settings

try:
    # Initialize OpenRouter using OpenAI compatible endpoint
    llm = ChatOpenAI(
        model=settings.MODEL_NAME, 
        temperature=0.3,
        api_key=settings.OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
        max_retries=0,
        timeout=10
    )
except Exception as e:
    llm = None

def get_smart_quiz_fallback(error_type):
    return [
        {
            "question": f"Regarding '{error_type}', what is the best practice?",
            "options": ["Check operators and boundaries carefully", "Ignore the warning", "Use global variables", "Write a longer code"],
            "correct_answer": "Check operators and boundaries carefully",
            "explanation": "Understanding your exact syntax and logic limits prevents runtime errors."
        },
        {
            "question": "If you see a logic error in your condition, what should you verify first?",
            "options": ["The comparison operator (e.g., == vs =)", "The package imports", "The variable names", "The class access modifiers"],
            "correct_answer": "The comparison operator (e.g., == vs =)",
            "explanation": "Conditionals rely on boolean expressions. Using assignment (=) breaks the logic."
        },
        {
            "question": "What is the primary cause of boundary errors?",
            "options": ["Using <= instead of < for array lengths", "Using print statements", "Declaring too many variables", "Using public classes"],
            "correct_answer": "Using <= instead of < for array lengths",
            "explanation": "Since Java arrays start at 0, using <= array.length will cause an OutOfBounds exception."
        },
        {
            "question": "How can you best debug a conditional logical error?",
            "options": ["Trace the variable values step-by-step", "Restart the computer", "Delete the code", "Change all variables to strings"],
            "correct_answer": "Trace the variable values step-by-step",
            "explanation": "Tracing helps you understand exactly what the condition evaluates to at runtime."
        }
    ]

def validate_and_format_quiz(data, error_type):
    try:
        if isinstance(data, dict):
            if "questions" in data:
                data = data["questions"]
            elif "quiz" in data:
                data = data["quiz"]
            else:
                return get_smart_quiz_fallback(error_type)
        
        if not isinstance(data, list) or len(data) == 0:
            return get_smart_quiz_fallback(error_type)
            
        for q in data:
            if not isinstance(q, dict):
                return get_smart_quiz_fallback(error_type)
                
            if "choices" in q and "options" not in q:
                q["options"] = q["choices"]
            if "answer" in q and "correct_answer" not in q:
                q["correct_answer"] = q["answer"]
                
            if "options" not in q or not isinstance(q["options"], list):
                return get_smart_quiz_fallback(error_type)
                
        return data
    except Exception as e:
        print(f"❌ Quiz Validation Error: {e}")
        return get_smart_quiz_fallback(error_type)

def generate_validation_quiz(student_id: str, error_type: str, code_snippet: str):
    if not settings.OPENROUTER_API_KEY:
        return get_smart_quiz_fallback(error_type)

    prompt_template = """
    You are 'Code Guru', an expert computer science tutor.
    The student specifically struggled with this error: "{error_type}"
    Their exact code was: "{code_snippet}"

    CRITICAL INSTRUCTION: You MUST generate exactly 4 multiple choice questions that test their knowledge ONLY on the concept of "{error_type}". Do not ask generic Java questions. Make them specific to the mistake they made.

    Return the response EXACTLY as a JSON array of objects.
    [
        {{
            "question": "Specific question about {error_type}?",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "correct_answer": "Option B",
            "explanation": "Clear explanation."
        }}
    ]
    """

    prompt = PromptTemplate(
        input_variables=["student_id", "error_type", "code_snippet"],
        template=prompt_template
    )

    formatted_prompt = prompt.format(student_id=student_id, error_type=error_type, code_snippet=code_snippet)
    content = ""

    try:
        response = llm.invoke(formatted_prompt)
        content = response.content
        print("✅ Quiz Generation: Using LangChain (OpenRouter)")
    except Exception as e:
        print(f"⚠️ Quiz LangChain Failed: {e}. Switching to OpenRouter Fallback API...")
        try:
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            }
            data = {
                "model": settings.MODEL_NAME,
                "messages": [{"role": "user", "content": formatted_prompt}],
                "temperature": 0.3
            }
            res = requests.post(url, headers=headers, json=data, timeout=10)
            if res.status_code == 200:
                content = res.json()['choices'][0]['message']['content']
            else:
                raise Exception("API Request Failed")
        except Exception as fallback_error:
            print(f"⚠️ Quiz Fallback API Failed: {fallback_error}. Serving Mock Data.")
            return get_smart_quiz_fallback(error_type)

    if isinstance(content, list) and len(content) > 0 and isinstance(content[0], dict) and 'text' in content[0]:
        content = content[0]['text']

    try:
        parsed_data = None
        if isinstance(content, list):
            parsed_data = content
        elif isinstance(content, dict):
            parsed_data = content
        elif isinstance(content, str):
            content = content.replace("```json", "").replace("```", "").strip()
            start_index = content.find('[')
            end_index = content.rfind(']')
            
            if start_index != -1 and end_index != -1:
                clean_json = content[start_index:end_index+1]
                parsed_data = json.loads(clean_json)
            else:
                start_idx_dict = content.find('{')
                end_idx_dict = content.rfind('}')
                if start_idx_dict != -1 and end_idx_dict != -1:
                    clean_json = content[start_idx_dict:end_idx_dict+1]
                    parsed_data = json.loads(clean_json)
        
        if parsed_data is not None:
            return validate_and_format_quiz(parsed_data, error_type)
        else:
            return get_smart_quiz_fallback(error_type)

    except Exception as parse_error:
        print(f"❌ Quiz JSON Parsing Error: {parse_error}")
        return get_smart_quiz_fallback(error_type)