import re
import numpy as np

def extract_features(code: str) -> np.ndarray:
    """
    Extracts stylistic features from code string.
    Returns feature vector for scikit-learn.
    """
    features = []
    
    # 1. Average line length
    lines = code.split('\n')
    avg_len = np.mean([len(l) for l in lines]) if lines else 0
    features.append(avg_len)
    
    # 2. Comment density
    comment_lines = len([l for l in lines if l.strip().startswith('#') or l.strip().startswith('//')])
    density = comment_lines / len(lines) if lines else 0
    features.append(density)
    
    # 3. Snake case vs Camel Case ratio (heuristic)
    snake_case = len(re.findall(r'[a-z]+_[a-z]+', code))
    camel_case = len(re.findall(r'[a-z]+[A-Z][a-z]+', code))
    ratio = snake_case / (camel_case + 1)
    features.append(ratio)
    
    # 4. Keyword usage (very basic for prototype)
    # AI often uses specific patterns or standard library imports
    features.append(code.count('import '))
    features.append(code.count('def '))
    features.append(code.count('class '))
    
    return np.array(features).reshape(1, -1)
