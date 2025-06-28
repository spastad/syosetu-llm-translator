# logger.py
"""
Module for setting up and using the logger.
"""
import sys
from datetime import datetime

def setup_encoding():
    """Sets UTF-8 encoding for stdout and stderr."""
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

def log_message(message: str):
    """Logs message to terminal and logs.txt file with timestamps."""
    current_time = datetime.now()
    term_time = current_time.strftime("%H:%M")
    log_time = current_time.strftime("%Y-%m-%d %H:%M:%S")

    term_prefix = f"[{term_time}] "
    log_prefix = f"[{log_time}] "

    lines = message.split('\n')
    
    # Format output for terminal and file with proper indentation
    term_output = term_prefix + lines[0]
    log_output = log_prefix + lines[0]
    
    for line in lines[1:]:
        term_output += f"\n{' ' * len(term_prefix)}{line}"
        log_output += f"\n{' ' * len(log_prefix)}{line}"
    
    print(term_output)
    
    with open("logs.txt", "a", encoding="utf-8") as log_file:
        log_file.write(log_output + "\n")