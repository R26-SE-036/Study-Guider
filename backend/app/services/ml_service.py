import os
import joblib
import pandas as pd
import javalang

from app.services.cognitive_rubric import classify as rubric_classify

# Define paths to load the trained model
base_dir = os.path.dirname(os.path.abspath(__file__))
model_path = os.path.join(base_dir, "models", "cognitive_model.pkl")

# ── Loading ───────────────────────────────────────────────────────────────────
# ml_model_trainer.py writes {"model", "feature_columns", "card"}. A bare
# estimator is the pre-rewrite artifact - fitted on ten handwritten rows with a
# different feature order - so it is refused by name rather than served.
_bundle = None
try:
    _loaded = joblib.load(model_path)
    if isinstance(_loaded, dict) and "model" in _loaded:
        _bundle = _loaded
        print(
            "Cognitive model loaded "
            f"({_bundle['card'].get('label_provenance', 'unknown')}-labelled)."
        )
    else:
        print(
            "cognitive_model.pkl is in the pre-rewrite format (a bare estimator "
            "fitted on ten handwritten rows). Refusing to use it; the rubric "
            "answers instead. Run: python -m app.services.ml_model_trainer"
        )
except Exception as error:
    print(f"Cognitive model could not be loaded ({error}); the rubric answers instead.")


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
    """The student's cognitive state, used only to set the lesson's register.

    Falls back to the rubric the model was fitted on - NOT to a fixed string.
    This used to return "Needs Simple Basics" whenever the model was missing or
    threw, which meant a service with no model at all still answered every
    request with a confident-looking constant, and every lesson came out pitched
    for a beginner. The rubric is what the model approximates, so falling back to
    it degrades smoothly instead of silently.

    See app/services/cognitive_rubric.py for what the label means and how much
    weight it is meant to carry.
    """
    complexity_score = extract_code_complexity(code_snippet)

    if _bundle is None:
        state = rubric_classify(error_count, complexity_score, past_score)
        print(f"Cognitive state (rubric, no model): {state} | complexity {complexity_score}")
        return state

    try:
        features = pd.DataFrame(
            [[error_count, complexity_score, past_score]],
            columns=_bundle["feature_columns"],
        )
        prediction = str(_bundle["model"].predict(features)[0])
        print(f"Cognitive state (model): {prediction} | complexity {complexity_score}")
        return prediction
    except Exception as error:
        state = rubric_classify(error_count, complexity_score, past_score)
        print(f"Cognitive model failed ({error}); rubric says {state}.")
        return state
