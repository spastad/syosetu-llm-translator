import re
import os
import argparse
from pathlib import Path

def is_header(line):
    """Checks if a line is a Markdown header"""
    stripped = line.lstrip()
    if not stripped.startswith('#'):
        return False
    header_chars = 0
    for char in stripped:
        if char == '#':
            header_chars += 1
        else:
            break
    return 1 <= header_chars <= 6 and (
        header_chars == len(stripped) or stripped[header_chars] in [' ', '\t']
    )

def is_list_item(line):
    """Checks if a line is a Markdown list item"""
    stripped = line.lstrip()
    # Check unordered lists
    if re.match(r'^([-*+])\s', stripped):
        return True
    # Check ordered lists
    if re.match(r'^\d+\.\s', stripped):
        return True
    return False

def process_md_content(lines):
    """Processes Markdown content by adding spaces to line breaks"""
    processed = []
    total_lines = len(lines)
    
    for i, line in enumerate(lines):
        # Preserve original line endings
        line_end = ''
        if line.endswith('\r\n'):
            content = line[:-2]
            line_end = '\r\n'
        elif line.endswith('\n'):
            content = line[:-1]
            line_end = '\n'
        else:
            content = line

        # Skip empty lines
        if content.strip() == '':
            processed.append(line)
            continue

        # Skip headers and lists
        if is_header(content) or is_list_item(content):
            processed.append(line)
            continue

        # If this is the last line or next line is empty - skip processing
        is_last_line = (i == total_lines - 1)
        next_line_empty = False
        
        if not is_last_line:
            next_line = lines[i+1]
            next_line_empty = (next_line.strip() == '')
        
        if is_last_line or next_line_empty:
            processed.append(line)
        else:
            # Remove existing trailing spaces and add exactly two
            new_content = content.rstrip() + '  ' + line_end
            processed.append(new_content)
    
    return processed

def process_file(input_path, output_path):
    """Processes a single Markdown file"""
    with open(input_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    processed_lines = process_md_content(lines)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.writelines(processed_lines)

def main():
    parser = argparse.ArgumentParser(
        description='Adds spaces to line breaks in Markdown files',
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('input', help='Input file or directory')
    parser.add_argument('output', nargs='?', default=None, help='Output file or directory (optional)')
    
    args = parser.parse_args()
    
    # Windows path support
    input_path = Path(args.input)
    
    # Process single file
    if input_path.is_file():
        output_path = Path(args.output) if args.output else input_path
        
        # If output directory specified
        if args.output and Path(args.output).is_dir():
            output_path = Path(args.output) / input_path.name
        
        process_file(input_path, output_path)
        print(f"Processed: {input_path} -> {output_path}")
    
    # Process directory
    elif input_path.is_dir():
        output_dir = Path(args.output) if args.output else input_path
        
        # Create output directory if needed
        if args.output and not output_dir.exists():
            output_dir.mkdir(parents=True, exist_ok=True)
        
        # Process all .md files in directory
        for md_file in input_path.glob('*.md'):
            output_path = output_dir / md_file.name
            process_file(md_file, output_path)
            print(f"Processed: {md_file} -> {output_path}")
    
    else:
        print(f"Error: '{input_path}' is not a file or directory")
        exit(1)

if __name__ == "__main__":
    main()