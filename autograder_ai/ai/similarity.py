import os
import re
from typing import List, Tuple

class SimilarityEngine:
    def __init__(self, n: int = 3):
        self.n = n

    def _tokenize(self, content: str) -> List[str]:
        # Simple tokenization: remove comments, split by whitespace
        # Production would use AST parsing
        content = re.sub(r'#.*', '', content) # Python comments
        content = re.sub(r'//.*', '', content) # Java comments
        return content.lower().split()

    def _get_ngrams(self, tokens: List[str]) -> set:
        if len(tokens) < self.n:
            return set()
        return set(tuple(tokens[i:i+self.n]) for i in range(len(tokens)-self.n+1))

    def check_similarity(self, submission_text: str, corpus_dir: str) -> List[Tuple[str, float]]:
        """
        Returns list of (filename, similarity_score)
        """
        sub_tokens = self._tokenize(submission_text)
        sub_ngrams = self._get_ngrams(sub_tokens)
        
        if not sub_ngrams:
            return []
            
        results = []
        
        # Walk through corpus (past submissions)
        # Note: In a real system, we'd use a database or pre-computed hashes
        for root, dirs, files in os.walk(corpus_dir):
            for file in files:
                try:
                    path = os.path.join(root, file)
                    with open(path, 'r', errors='ignore') as f:
                        corpus_text = f.read()
                        
                    corpus_tokens = self._tokenize(corpus_text)
                    corpus_ngrams = self._get_ngrams(corpus_tokens)
                    
                    if not corpus_ngrams:
                        continue
                        
                    intersection = len(sub_ngrams.intersection(corpus_ngrams))
                    union = len(sub_ngrams.union(corpus_ngrams))
                    jaccard = intersection / union if union > 0 else 0.0
                    
                    if jaccard > 0.5: # Threshold
                        results.append((file, jaccard))
                        
                except Exception:
                    continue
                    
        return sorted(results, key=lambda x: x[1], reverse=True)[:3]

    def check_similarity_from_texts(self, submission_text: str, corpus_texts: dict) -> List[Tuple[str, float]]:
        """
        Compares submission_text against a dictionary of {identifier: code_content}
        to avoid comparing against itself safely and extracting from ZIPs beforehand.
        """
        sub_tokens = self._tokenize(submission_text)
        sub_ngrams = self._get_ngrams(sub_tokens)
        
        if not sub_ngrams:
            return []
            
        results = []
        for identifier, corpus_text in corpus_texts.items():
            try:
                corpus_tokens = self._tokenize(corpus_text)
                corpus_ngrams = self._get_ngrams(corpus_tokens)
                
                if not corpus_ngrams:
                    continue
                    
                intersection = len(sub_ngrams.intersection(corpus_ngrams))
                union = len(sub_ngrams.union(corpus_ngrams))
                jaccard = intersection / union if union > 0 else 0.0
                
                if jaccard > 0.5: # Threshold
                    results.append((identifier, jaccard))
            except Exception:
                continue
                
        return sorted(results, key=lambda x: x[1], reverse=True)[:3]
