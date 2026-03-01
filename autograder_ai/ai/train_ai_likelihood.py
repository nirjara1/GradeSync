import os
import argparse
import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
from .features import extract_features

def load_data(data_dir: str):
    human_dir = os.path.join(data_dir, 'human')
    ai_dir = os.path.join(data_dir, 'ai')
    
    X = []
    y = []
    
    # Label 0: Human
    if os.path.exists(human_dir):
        for f in os.listdir(human_dir):
            try:
                with open(os.path.join(human_dir, f), 'r', errors='ignore') as file:
                    content = file.read()
                    feats = extract_features(content)
                    X.append(feats[0])
                    y.append(0)
            except Exception:
                continue
                
    # Label 1: AI
    if os.path.exists(ai_dir):
        for f in os.listdir(ai_dir):
            try:
                with open(os.path.join(ai_dir, f), 'r', errors='ignore') as file:
                    content = file.read()
                    feats = extract_features(content)
                    X.append(feats[0])
                    y.append(1)
            except Exception:
                continue
                
    return np.array(X), np.array(y)

def train_model(data_dir: str, output_path: str):
    print(f"Loading data from {data_dir}...")
    X, y = load_data(data_dir)
    
    if len(X) == 0:
        print("No training data found.")
        # Create a dummy model for the sake of the prototype if no data
        print("Creating dummy model...")
        X = np.random.rand(10, 5) # 5 features
        y = np.random.randint(0, 2, 10)
    
    print(f"Training on {len(X)} samples...")
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    clf = RandomForestClassifier(n_estimators=100, random_state=42)
    clf.fit(X_train, y_train)
    
    y_pred = clf.predict(X_test)
    print(f"Accuracy: {accuracy_score(y_test, y_pred)}")
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    joblib.dump(clf, output_path)
    print(f"Model saved to {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--data_dir', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    
    train_model(args.data_dir, args.out)
