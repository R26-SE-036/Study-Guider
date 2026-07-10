import os
import joblib
import pandas as pd
import javalang

# Define paths to load the trained model
base_dir = os.path.dirname(os.path.abspath(__file__))
model_path = os.path.join(base_dir, "models", "cognitive_model.pkl")

# Load the trained Random Forest model into memory
try:
    rf_model = joblib.load(model_path)
    print("✅ ML Model Loaded Successfully!")
except Exception as e:
    print(f"⚠️ Warning: ML Model could not be loaded: {e}")
    rf_model = None

def extract_code_complexity(code_snippet: str) -> int:
    """
    Java-specific feature extraction using Abstract Syntax Tree (AST).
    Programmatically counts control structures to calculate a Complexity Score.
    """
    try:
        # Beginners often write just snippets. javalang needs a valid class structure to parse.
        if "class " not in code_snippet:
            java_code = f"public class TempClass {{ public void tempMethod() {{ {code_snippet} }} }}"
        else:
            java_code = code_snippet

        # Generate the AST
        tree = javalang.parse.parse(java_code)
        complexity = 0

        # Traverse the AST nodes to count exact features
        for path, node in tree:
            # Count Loops and Conditions
            if isinstance(node, (javalang.tree.ForControl, 
                                 javalang.tree.WhileStatement, 
                                 javalang.tree.IfStatement, 
                                 javalang.tree.SwitchStatement)):
                complexity += 2
            # Count Assignments
            elif isinstance(node, javalang.tree.Assignment):
                complexity += 1
            # Count Boolean/Logical Operators
            elif isinstance(node, javalang.tree.BinaryOperation):
                if node.operator in ['&&', '||', '==', '!=', '<', '>', '<=', '>=']:
                    complexity += 1
            # 🔴 FIXED: Correct javalang class for array indexing
            elif isinstance(node, javalang.tree.ArraySelector):
                complexity += 1

        # Fallback if no specific structures found but code exists
        if complexity == 0:
            complexity = 2
            
        return max(1, min(complexity, 20))
        
    except Exception as e:
        # If code is completely syntactically broken, assign a default baseline complexity
        print(f"⚠️ AST Parsing Error (Invalid Syntax): {e}")
        return 2

def predict_cognitive_state(error_count: int, code_snippet: str, past_score: int) -> str:
    if rf_model is None:
        return "Needs Simple Basics"
        
    # 1. Feature Extraction via AST
    complexity_score = extract_code_complexity(code_snippet)
    
    # 2. Prepare features as a Pandas DataFrame
    features = pd.DataFrame(
        [[error_count, complexity_score, past_score]], 
        columns=['error_count', 'complexity_score', 'past_score']
    )
    
    try:
        # 3. Model Prediction
        prediction = rf_model.predict(features)[0]
        print(f"🧠 ML Prediction -> Cognitive State: {prediction} | AST Complexity Score: {complexity_score}")
        return prediction
    except Exception as e:
        print(f"❌ Prediction Error: {e}")
        return "Needs Simple Basics"