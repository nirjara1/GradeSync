"""
Structural Plagiarism Engine – Winnowing Fingerprinting (MOSS-style)

Architecture
------------
Three-stage pipeline, identical to the one used by Stanford MOSS:

  1. Normalize  – strip comments/imports, collapse whitespace, replace every
                  user-defined identifier with the single char 'V'.
  2. Hash       – slide a window of k chars over the normalized text and hash
                  each slice with zlib.adler32 (fast, no external deps).
  3. Winnow     – slide a window of w hashes and record the minimum in each
                  position. The resulting deduplicated set of integers is the
                  file's *fingerprint*.

Comparing fingerprints is O(|A|+|B|) integer-set intersection — roughly
1 000× faster than comparing sets of string n-gram tuples.

Similarity metric: containment (not Jaccard)
    score = |A ∩ B| / min(|A|, |B|)
Containment is more sensitive to partial copies and better matches what MOSS
reports.

Public API (unchanged from the previous engine so callers don't break):
    SimilarityEngine.fingerprint(text)                       → frozenset[int]
    SimilarityEngine.check_similarity(text, corpus_dir)      → list[tuple]
    SimilarityEngine.check_similarity_from_texts(text, dict) → list[tuple]
    SimilarityEngine.bulk_compare(submissions)               → dict
"""

import os
import re
import zlib
from typing import Dict, FrozenSet, List, Set, Tuple


class SimilarityEngine:
    """
    Winnowing fingerprint-based plagiarism engine.

    Parameters
    ----------
    k : int
        k-gram (substring) length for hashing. Default 25 characters gives
        a good balance between sensitivity and fingerprint size.
    w : int
        Sliding-window size for the winnowing step. Larger values produce
        smaller, coarser fingerprints. Default 4.
    """

    # Structural keywords kept verbatim after normalisation.
    KEYWORDS: Set[str] = {
        # Python
        'def', 'if', 'else', 'elif', 'while', 'for', 'return', 'class',
        'try', 'except', 'finally', 'with', 'pass', 'break', 'continue',
        'lambda', 'yield', 'and', 'or', 'not', 'in', 'is',
        # Java
        'public', 'private', 'protected', 'static', 'final', 'void',
        'int', 'double', 'float', 'long', 'short', 'byte', 'boolean',
        'char', 'new', 'this', 'super', 'extends', 'implements',
        'throws', 'throw', 'catch', 'instanceof', 'interface', 'abstract',
        'enum', 'switch', 'case', 'default', 'do', 'synchronized',
        # Operators stay in the normalised text as individual char tokens
    }

    def __init__(self, k: int = 25, w: int = 4):
        self.k = k
        self.w = w

    # ------------------------------------------------------------------
    # Stage 1 – Normalise
    # ------------------------------------------------------------------
    def _normalize(self, source: str) -> str:
        """
        Return a compact, identifier-agnostic representation of *source*.

        Steps
        -----
        1. Strip single-line and multi-line comments.
        2. Strip import / package / main boilerplate.
        3. Tokenize: keep structural keywords and punctuation verbatim;
           replace every user-defined identifier with 'V'.
        4. Join tokens with a single space.
        """
        # --- Strip comments ---
        source = re.sub(r'#[^\n]*', '', source)                      # Python
        source = re.sub(r'//[^\n]*', '', source)                     # Java
        source = re.sub(r'/\*.*?\*/', '', source, flags=re.DOTALL)   # /* … */

        # --- Strip boilerplate ---
        source = re.sub(r'^\s*import\s+[\w.*]+\s*;?\s*$',  '', source, flags=re.MULTILINE)
        source = re.sub(r'^\s*from\s+[\w.]+\s+import\s+[\w.*]+\s*$', '', source, flags=re.MULTILINE)
        source = re.sub(r'^\s*package\s+[\w.]+\s*;\s*$',   '', source, flags=re.MULTILINE)
        source = re.sub(
            r'public\s+static\s+void\s+main\s*\(.*?\)\s*(?:throws\s+\w+\s*)?',
            '', source, flags=re.DOTALL
        )
        source = re.sub(r'if\s+__name__\s*==\s*["\']__main__["\']\s*:\s*', '', source)

        # --- Tokenize and replace identifiers ---
        raw_tokens = re.findall(
            r'[a-zA-Z_][a-zA-Z0-9_]*|==|!=|<=|>=|[=+\-*/(){}[\];.,<>!&|^~]|\d+',
            source
        )
        normalised_tokens: List[str] = []
        for tok in raw_tokens:
            if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', tok) and tok.lower() not in self.KEYWORDS:
                normalised_tokens.append('V')
            else:
                normalised_tokens.append(tok.lower())

        return ' '.join(normalised_tokens)

    # ------------------------------------------------------------------
    # Stage 2 – Hash k-grams
    # ------------------------------------------------------------------
    def _hash_kgrams(self, text: str) -> List[int]:
        """
        Slide a window of *k* characters over *text* and hash each slice.

        Uses zlib.adler32: fast, zero external dependencies, good distribution.
        Returns an empty list when ``len(text) < k``.
        """
        if len(text) < self.k:
            return []
        return [
            zlib.adler32(text[i: i + self.k].encode()) & 0xFFFFFFFF
            for i in range(len(text) - self.k + 1)
        ]

    # ------------------------------------------------------------------
    # Stage 3 – Winnow
    # ------------------------------------------------------------------
    def _winnow(self, hashes: List[int]) -> FrozenSet[int]:
        """
        Apply the Winnowing algorithm (Schleimer et al. 2003) to *hashes*.

        For each window of size *w*, record the minimum hash.  The resulting
        deduplicated set of integers is the fingerprint of the document.
        """
        if len(hashes) < self.w:
            # Fewer hashes than window size – use all of them.
            return frozenset(hashes)

        fingerprint: Set[int] = set()
        prev_min_idx = -1

        for i in range(len(hashes) - self.w + 1):
            window = hashes[i: i + self.w]
            # Rightmost occurrence of the minimum (rightmost = most stable)
            min_val = min(window)
            # Find rightmost index of min_val inside the window
            min_idx_in_window = max(j for j, h in enumerate(window) if h == min_val)
            global_idx = i + min_idx_in_window

            if global_idx != prev_min_idx:
                fingerprint.add(min_val)
                prev_min_idx = global_idx

        return frozenset(fingerprint)

    # ------------------------------------------------------------------
    # Similarity metric
    # ------------------------------------------------------------------
    @staticmethod
    def _containment(a: FrozenSet[int], b: FrozenSet[int]) -> float:
        """
        Containment similarity: |A ∩ B| / min(|A|, |B|).

        More sensitive to partial copies than Jaccard.
        Returns 0.0 when either set is empty.
        """
        if not a or not b:
            return 0.0
        intersection = len(a & b)
        return intersection / min(len(a), len(b))

    # ------------------------------------------------------------------
    # Public API – fingerprint (cacheable)
    # ------------------------------------------------------------------
    def fingerprint(self, text: str) -> FrozenSet[int]:
        """
        Return the Winnowing fingerprint (frozenset of ints) for *text*.

        This is the primary cacheable artifact.  Comparing two fingerprints
        is an O(min(|A|,|B|)) integer-set operation.
        """
        normalised = self._normalize(text)
        hashes = self._hash_kgrams(normalised)
        return self._winnow(hashes)

    # ------------------------------------------------------------------
    # Public API – compare against a directory
    # ------------------------------------------------------------------
    def check_similarity(
        self, submission_text: str, corpus_dir: str
    ) -> List[Tuple[str, float]]:
        """Compare *submission_text* against every file in *corpus_dir*."""
        sub_fp = self.fingerprint(submission_text)
        if not sub_fp:
            return []

        results: List[Tuple[str, float]] = []
        for root, _dirs, files in os.walk(corpus_dir):
            for fname in files:
                try:
                    with open(os.path.join(root, fname), 'r', errors='ignore') as fh:
                        corpus_fp = self.fingerprint(fh.read())
                    score = self._containment(sub_fp, corpus_fp)
                    if score > 0.05:
                        results.append((fname, score))
                except Exception:
                    continue

        return sorted(results, key=lambda x: x[1], reverse=True)[:3]

    # ------------------------------------------------------------------
    # Public API – compare against an in-memory corpus dict
    # ------------------------------------------------------------------
    def check_similarity_from_texts(
        self,
        submission_text: str,
        corpus_texts: Dict[str, str],
    ) -> List[Tuple[str, float]]:
        """
        Args:
            submission_text: raw source code of the submission being checked.
            corpus_texts: {identifier: source_code} for all other submissions.

        Returns:
            Sorted list of (identifier, score) – highest first, top-3.
        """
        sub_fp = self.fingerprint(submission_text)
        if not sub_fp:
            return []

        results: List[Tuple[str, float]] = []
        for identifier, corpus_text in corpus_texts.items():
            try:
                corpus_fp = self.fingerprint(corpus_text)
                score = self._containment(sub_fp, corpus_fp)
                if score > 0.05:
                    results.append((identifier, score))
            except Exception:
                continue

        return sorted(results, key=lambda x: x[1], reverse=True)[:3]

    # ------------------------------------------------------------------
    # Public API – bulk compare (O(N) fingerprinting + O(N²) int sets)
    # ------------------------------------------------------------------
    def bulk_compare(
        self,
        submissions: Dict[str, str],
    ) -> Dict[str, List[Tuple[str, float]]]:
        """
        Compare every submission against every other in one pass.

        Args:
            submissions: {submission_id: source_code}

        Returns:
            {submission_id: [(matched_id, score), ...]} – top-3 matches each.

        Complexity
        ----------
        O(N) hashing step (fingerprints computed once) followed by O(N²)
        integer-set intersections.  Integer-set operations are ~1 000× faster
        than the previous string n-gram comparisons.
        """
        # --- O(N): compute all fingerprints once ---
        fingerprints: Dict[str, FrozenSet[int]] = {
            sid: self.fingerprint(code)
            for sid, code in submissions.items()
        }

        ids = list(fingerprints.keys())
        results: Dict[str, List[Tuple[str, float]]] = {}

        # --- O(N²): compare every pair (upper-triangle only) ---
        scores: Dict[Tuple[str, str], float] = {}
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = ids[i], ids[j]
                score = self._containment(fingerprints[a], fingerprints[b])
                if score > 0.05:
                    scores[(a, b)] = score

        # Build per-submission match list from the scored pairs
        for sid in ids:
            matches: List[Tuple[str, float]] = []
            for (a, b), score in scores.items():
                if a == sid:
                    matches.append((b, score))
                elif b == sid:
                    matches.append((a, score))
            results[sid] = sorted(matches, key=lambda x: x[1], reverse=True)[:3]

        return results
