import os
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import joblib

# Import the AST complexity extraction function from our ML service
from app.services.ml_service import extract_code_complexity

# Define base directories and paths
base_dir = os.path.dirname(os.path.abspath(__file__))
model_dir = os.path.join(base_dir, "models")
model_path = os.path.join(model_dir, "cognitive_model.pkl")

# Path to our new real dataset in the data folder
data_path = os.path.join(os.path.dirname(os.path.dirname(base_dir)), "data", "dataset.csv")

def train_and_save_model():
    """
    Trains the Random Forest model using the real dataset.
    Calculates code complexity on the fly using AST.
    """
    if not os.path.exists(model_dir):
        os.makedirs(model_dir)

    print("⏳ Loading real dataset from CSV...")
    if not os.path.exists(data_path):
        print(f"❌ Dataset not found at: {data_path}")
        return

    # Load the CSV data into a Pandas DataFrame
    dataset = pd.read_csv(data_path)

    print("⏳ Calculating AST complexity scores for the dataset...")
    # Apply the AST function to calculate complexity for each code snippet
    dataset['complexity_score'] = dataset['code_snippet'].apply(extract_code_complexity)

    # Define Features (X) and Target Label (y)
    X = dataset[['error_count', 'complexity_score', 'past_score']]
    y = dataset['cognitive_state']

    # Split the data into training (80%) and testing (20%) sets
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    print("⏳ Training Random Forest Classifier with AST features...")
    # Initialize and train the Random Forest model
    rf_model = RandomForestClassifier(n_estimators=100, random_state=42)
    rf_model.fit(X_train, y_train)

    # Evaluate the model accuracy using the test set
    predictions = rf_model.predict(X_test)
    accuracy = accuracy_score(y_test, predictions)
    print(f"✅ Model trained successfully! Accuracy: {accuracy * 100:.2f}%")

    # Save the trained model as a .pkl file for future predictions
    joblib.dump(rf_model, model_path)
    print(f"✅ Model saved securely at: {model_path}")

if __name__ == "__main__":
    print("🚀 Starting ML Model Training Process with Real Data...")
    train_and_save_model()