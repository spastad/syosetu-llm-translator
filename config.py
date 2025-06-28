# config.py
"""
Central configuration file for the translator.
"""

# API settings
API_CONFIG = {
    "chutes": {
        "url": "https://llm.chutes.ai/v1/chat/completions",
        "model": "deepseek-ai/DeepSeek-R1-0528"
    },
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "model": "deepseek/deepseek-r1-0528:free"
    }
}

# API request parameters
REQUEST_TIMEOUT_SECONDS = 11 * 60
DEFAULT_TEMPERATURE = 0.1

# Logic settings
MAX_TRANSLATION_ATTEMPTS = 50
GENERAL_DELAY_SECONDS = 5  # Delay between attempts and between chapters

# Markers for parsing LLM response
THINK_BLOCK_PATTERN = r'<think>.*?</think>'
NOTES_MARKER = "#### === Chapter Notes ==="
MD_TRANSLATION_MARKER = "#### === Markdown Translation ==="
CHAPTER_TRANSLATION_NOTES_MARKER = "### Chapter Translation Notes"

# Response size validation parameters
TRANSLATION_SIZE_MIN_RATIO = 1.35
TRANSLATION_SIZE_MAX_RATIO = 3.30

# Notes processing settings
# Phrases that skip notes update
NOTES_SKIP_PHRASES = {"(none new)", "(none)", "[none new]", "[none]"}
# Maximum number of lines for chapter-specific notes (newest are preserved)
MAX_CHAPTER_SPECIFIC_NOTE_LINES = 50
# Header for chapter-specific notes file
CHAPTER_SPECIFIC_NOTES_HEADER = "=== FIXED Chapter-specific Notes ==="
# Keys and filename templates for all note types
NOTE_FILE_TEMPLATES = {
    "static": "fixed_notes_{novel_id}.txt",
    "chars": "fixed_character_names_{novel_id}.txt",
    "terms": "fixed_special_terms_{novel_id}.txt",
    "chapter_specific": "fixed_chapter_specific_notes_{novel_id}.txt"
}
# Regular expressions for section headers in LLM response
NOTE_SECTION_PATTERNS = {
    "characters": r"===\s*Character Names\s*===(.*?)(?:===\s*|$)",
    "terms": r"===\s*Special Terms\s*===(.*?)(?:===\s*|$)",
    "chapter_specific": r"===\s*Chapter-specific Notes\s*===(.*?)(?:===\s*|$)"
}

# Other settings
NOVEL_DIR_PREFIX = "tn_"
BACKUP_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"

# Translated filename template
TRANSLATED_FILENAME_TEMPLATE = "tn_{novel_id}_part_{part_num}.md"

# Backup settings
BACKUPS_SUBDIR = "backups"
BACKUP_DIR_TEMPLATE = "{timestamp}_part_{part_num}"
SCRIPTS_TO_BACKUP = [
    'config.py',
    'translator.py',
    'logger.py',
    'markdown_fix.py'
]
BACKUP_FILES = {
    "prompt_template": "prompt_template.txt",
    "final_prompt": "final_llm_prompt_part_{part_num}.txt",
    "original_chapter": "original_chapter_part_{part_num}.txt",
    "llm_response": "llm_full_response_part_{part_num}.txt",
    "translation": "translation_part_{part_num}.md"
}