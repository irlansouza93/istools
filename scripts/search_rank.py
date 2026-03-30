import os
import re

patterns = [
    re.compile(r'3°\s*Sgt', re.IGNORECASE),
    re.compile(r'3º\s*Sgt', re.IGNORECASE),
    re.compile(r'3rd\s*Sgt', re.IGNORECASE),
    re.compile(r'3[o°]\s*Sgt', re.IGNORECASE),
    re.compile(r'3\s*Sgt', re.IGNORECASE)
]

def check_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            for pattern in patterns:
                if pattern.search(content):
                    print(f"FOUND in {filepath}: {pattern.pattern}")
                    # Print lines
                    f.seek(0)
                    for i, line in enumerate(f, 1):
                        if pattern.search(line):
                            print(f"  Line {i}: {line.strip()}")
    except Exception as e:
        # Ignore binary or encoding errors
        pass

def main():
    root = "istools"
    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            if filename.endswith(('.py', '.txt', '.md', '.qrc', '.cfg', '.rst')):
                check_file(os.path.join(dirpath, filename))

if __name__ == "__main__":
    main()
