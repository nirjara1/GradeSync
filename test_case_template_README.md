# Test Case CSV Format — Expected vs Actual Output

## CSV columns

| Column           | Description |
|------------------|-------------|
| **input_data**   | Exactly what the program will receive on **stdin** (e.g. the values for each `input()` call, one per line). |
| **expected_output** | The exact **stdout** the program must produce for the run to **pass**. |
| **is_private**   | `true` = hidden from students (instructor-only); `false` = visible. |
| **points**       | Points awarded when the test passes. |

The grader runs the student’s code once per row, feeds **input_data** as stdin, and compares the program’s stdout to **expected_output**. If they match (after stripping), the test **passes**; otherwise you see **Expected output** vs **Actual output** in the Test Runner.

---

## Example 1: Simple (template — sum of three numbers)

- **input_data:** `1 2 3`  
  (one line: three numbers)
- **expected_output:** `6`
- **Meaning:** Program reads three numbers and prints their sum.

---

## Example 2: Word Tester (menu + palindrome + quit)

For an assignment that prints a menu, then asks for a word, then prints a result and says GOODBYE:

- **input_data** (one line per `input()` in order, e.g. choice → word → quit):

  ```text
  1
  racecar
  3
  ```

  In the CSV you can store this as either:
  - A single cell with real newlines, or  
  - A single cell with literal `\n`, e.g. `"1\nracecar\n3"` (the grader converts `\n` to newlines).

- **expected_output** (exactly what stdout should be for that run):

  ```text
  =====
  Word Tester
  =====
  ======================
  Choose Test
  =-=-=-=-=-=
  1. Palindrome
  2. Vowels vs Consonants
  3. Quit
  Enter choice (1-3): 
  Enter a word in lowercase letters: 
  'racecar' is a palindrome!
  ======================
  Choose Test
  =-=-=-=-=-=
  1. Palindrome
  2. Vowels vs Consonants
  3. Quit
  Enter choice (1-3): 
  GOODBYE!
  ======================
  ```

In the Test Runner UI:

- **Expected output** = this full block (from the CSV **expected_output**).
- **Actual output** = what the student’s program actually printed. If it matches the expected block (after stripping), the test passes; otherwise you see the diff (expected vs actual).

---

## If you see “can't open /code/input.txt”

The grader now feeds stdin from the test case CSV **without** using a file in the container (input is passed via environment and decoded inside the container). Restart the backend so it uses the updated sandbox; after that, this error should stop and you’ll get real **Actual output** instead.
