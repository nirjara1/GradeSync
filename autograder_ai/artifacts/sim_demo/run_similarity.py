from pathlib import Path

# Import your project module
from autograder_ai.ai import similarity as sim

BASE = Path("autograder_ai/artifacts/sim_demo")

def main():
    a = BASE / "studentA" / "main.py"
    b = BASE / "studentB" / "main.py"
    c = BASE / "studentC" / "main.py"

    # We'll try a few likely function names (since I haven't opened your file).
    # One of these should exist; the script will tell you which.
    candidates = [
        ("score_files", lambda x, y: sim.score_files(str(x), str(y))),
        ("similarity_score_files", lambda x, y: sim.similarity_score_files(str(x), str(y))),
        ("similarity_score", lambda x, y: sim.similarity_score(a.read_text(), b.read_text())),
        ("compute_similarity", lambda x, y: sim.compute_similarity(str(x), str(y))),
    ]

    ok = False
    for name, fn in candidates:
        try:
            ab = fn(a, b)
            ac = fn(a, c)
            print(f"[OK] used sim.{name}")
            print("A vs B (expected HIGH):", ab)
            print("A vs C (expected LOWER):", ac)
            ok = True
            break
        except Exception as e:
            # Try next candidate
            last_err = e

    if not ok:
        print("[FAIL] Could not find a callable similarity function in autograder_ai.ai.similarity")
        print("Last error:", repr(last_err))
        print("Open autograder_ai/ai/similarity.py and tell me the function names, or paste the file.")

if __name__ == "__main__":
    main()
