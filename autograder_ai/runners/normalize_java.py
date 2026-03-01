import re
import os
import shutil

def normalize_java_files(submission_path: str):
    """
    Scans for .java files (or files that should be .java)
    Reads content to find 'public class ClassName' matches.
    Renames the file to ClassName.java if needed.
    """
    for root, dirs, files in os.walk(submission_path):
        for file in files:
            file_path = os.path.join(root, file)
            
            # Simple heuristic: if it ends in .java or looks like code
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                # Regex for "public class ClassName"
                match = re.search(r'public\s+class\s+(\w+)', content)
                if match:
                    class_name = match.group(1)
                    expected_name = f"{class_name}.java"
                    
                    if file != expected_name:
                        # Rename
                        new_path = os.path.join(root, expected_name)
                        shutil.move(file_path, new_path)
            except Exception:
                continue
