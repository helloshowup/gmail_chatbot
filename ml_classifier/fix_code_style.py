#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Code style fixer for ML classifier module
Runs basic PEP 8 fixes on Python files in the ml_classifier directory
"""

import re
from pathlib import Path

# Constants
MAX_LINE_LENGTH = 100
PY_FILE_PATTERN = r'.*\.py$'

# Files to process
ML_DIR = Path(__file__).parent
PYTHON_FILES = [f for f in ML_DIR.glob('*.py') if re.match(PY_FILE_PATTERN, f.name)]


def fix_long_lines(file_content):
    """Break overly long lines into multiple lines where possible."""
    # This is a simplified version - a real implementation would use ast parsing
    lines = file_content.split('\n')
    fixed_lines = []
    
    for line in lines:
        if len(line.rstrip()) > MAX_LINE_LENGTH:
            # Try to break at a logical point for function args or list items
            if '(' in line and ')' in line:
                # This is a very basic approach - a real solution would be more sophisticated
                fixed_line = line.replace(', ', ',\n' + ' ' * (line.find('(') + 1))
                fixed_lines.append(fixed_line)
            else:
                fixed_lines.append(line)  # Keep as is if we can't safely fix
        else:
            fixed_lines.append(line)
    
    return '\n'.join(fixed_lines)


def fix_variable_names(file_content):
    """Convert CamelCase variables to snake_case where appropriate."""
    # This is a simplified approach - in a real implementation we'd use the ast module
    lines = file_content.split('\n')
    fixed_lines = []
    
    # Pattern to match CamelCase constants that should be UPPER_SNAKE_CASE
    constant_pattern = re.compile(r'([A-Z][a-z0-9]*){2,}\s*=')
    
    for line in lines:
        # Skip lines in docstrings, comments or with function/class definitions
        if line.strip().startswith(('"""', "'''", '#', 'def ', 'class ')):
            fixed_lines.append(line)
            continue
            
        # Fix CamelCase constants to UPPER_SNAKE_CASE
        match = constant_pattern.search(line)
        if match:
            var_name = match.group(0)[:-1].strip()
            if var_name.isupper():
                fixed_lines.append(line)  # Already uppercase
                continue
                
            # Convert CamelCase to UPPER_SNAKE_CASE
            snake_case = re.sub(r'(?<!^)(?=[A-Z])', '_', var_name).upper()
            fixed_lines.append(line.replace(var_name, snake_case))
        else:
            fixed_lines.append(line)
    
    return '\n'.join(fixed_lines)


def fix_file(file_path):
    """Apply PEP 8 fixes to a single file."""
    print(f"Fixing {file_path}...")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Apply fixes
    fixed_content = fix_long_lines(content)
    fixed_content = fix_variable_names(fixed_content)
    
    # Write changes back to file
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(fixed_content)
    
    print(f"Fixed {file_path}")


def main():
    """Run PEP 8 fixes on all Python files in the ML classifier directory."""
    print(f"Found {len(PYTHON_FILES)} Python files to process")
    
    for file_path in PYTHON_FILES:
        fix_file(file_path)
    
    print("All files processed.")


if __name__ == "__main__":
    main()
