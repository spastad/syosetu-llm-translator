# LLM Translator for Syosetu Webnovels

A sophisticated translation pipeline for Japanese webnovels from Syosetu.com using Large Language Models (LLMs). The system preserves translation context through specialized note files and produces high-quality Markdown translations optimized for conversion to EPUB.

## Features

- **Context Preservation**: Maintains character names, special terms, and translation style across chapters
- **Validation System**: Ensures translation quality through structural and size validation
- **Error Recovery**: Automatic retries and detailed backups for failed translations
- **Markdown Output**: Produces clean, formatted Markdown - can be converted to EPUB using Calibre and merged with EpubMerge Calibre plugin
- **Age Verification Handling**: Automatically bypasses Syosetu's age verification
- **Advanced LLM Integration**: Uses DeepSeek-R1-0528 model by default (uncensored, ideal for 18+ content)
- **Provider Options**: Supports `chutes` (default, no rate limits) and `openrouter`
- **Smart Notes**: Automatic updates to character names, terms and chapter notes during translation

## Folder Structure for Translations

Each novel gets its own folder named `tn_<novel_id>` (e.g., `tn_n6098fe` for [https://novel18.syosetu.com/n6098fe/](https://novel18.syosetu.com/n6098fe/) - 18+ webnovel "Reborn in a Chastity Reversal World"). The folder contains:

1. **Fixed Notes** (`fixed_notes_n6098fe.txt`):
   - **Manually created** before starting translation
   - Translation style guidelines
   - General translation rules
   - Consistent terminology
   - See [tn_n6098fe/fixed_notes_n6098fe.txt](tn_n6098fe/fixed_notes_n6098fe.txt)

2. **Character Names** (`fixed_character_names_n6098fe.txt`):
   - **Automatically updated** during translation
   - Starts with header only:
   ```
   === FIXED Character Names ===
   ```
   - Populated with entries like:
   ```
   - [Name] ([Original]): [Gender, description]
   ```

3. **Special Terms** (`fixed_special_terms_n6098fe.txt`):
   - **Automatically updated** during translation
   - Starts with header only:
   ```
   === FIXED Special Terms ===
   ```
   - Populated with entries like:
   ```
   - [Translation] ([Original]): [Description]
   ```

4. **Chapter-specific Notes** (`fixed_chapter_specific_notes_n6098fe.txt`):
   - **Automatically updated** during translation (max 50 recent lines)
   - Starts with header only:
   ```
   === FIXED Chapter-specific Notes ===
   ```
   - Populated with notes like:
   ```
   - First note: `[Full English chapter title]`
      - Subsequent notes: Key events only (max 7 notes)
   ```

5. **Translated Chapters** (`tn_n6098fe_part_001.md`, `tn_n6098fe_part_002.md`, etc.):
   - Clean Markdown files
   - Preserve original structure (preface, main content, afterword)
   - Ready for EPUB conversion in Calibre

6. **Backups** (`backups/` folder):
   - Timestamped backups for each translation attempt
   - Includes original content, LLM responses, and prompts

## Usage

1. Prepare API keys in `api_key_<service>.txt` files (ex. `api_key_chutes.txt`)
2. **Create Fixed Notes** file (see example)
3. Run translator (default provider: chutes):
   ```bash
   # Process single part (example: part 1 of n6098fe)
   python translator.py https://novel18.syosetu.com/n6098fe/1/
   
   # Process part range (4-413 of n6098fe)
   python translator.py https://novel18.syosetu.com/n6098fe/ 4-413
   
   # Use openrouter provider for part 1
   python translator.py https://novel18.syosetu.com/n6098fe/1/ --service openrouter
   ```

## Requirements

- Python 3.9+
- Dependencies: 
  ```bash
  pip install requests beautifulsoup4 html2text regex
  ```

## Configuration

Edit `config.py` to:
- Adjust timeouts and retry settings
- Modify validation thresholds
- Configure backup preferences
- Customize note file templates
- Switch between providers (`chutes`/`openrouter`)