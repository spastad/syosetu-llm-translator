# translator.py
import argparse
import os
import re
import html2text
import sys
import time
import json
import shutil
import html as html_escape
import threading
from urllib.parse import urlparse
from pathlib import Path
from bs4 import BeautifulSoup, Comment
import requests
from datetime import datetime

# Import from local modules
import config
from logger import log_message, setup_encoding
from markdown_fix import process_file as process_md_file

# --- Utilities and regular expressions (unchanged) ---

JP_OR_CH_REGEX = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\u3400-\u4DBF\u20000-\u2A6DF\u2A700-\u2B73F\u2B740-\u2B81F\u2B820-\u2CEAF\u2CEB0-\u2EBEF\u2F800-\u2FA1F]')
EN_REGEX = re.compile(r'[a-zA-Z]')

def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    jp_or_ch_chars = len(JP_OR_CH_REGEX.findall(text))
    en_chars = len(EN_REGEX.findall(text))
    other_chars = len(text) - jp_or_ch_chars - en_chars  
    total_tokens_estimated = (jp_or_ch_chars * 0.6) + \
                             (en_chars * 0.3) + \
                             (other_chars * 0.3) # Assume other characters are estimated as English  
    return int(round(total_tokens_estimated))

def format_duration(seconds_float):
    total_seconds = round(seconds_float)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return (
        f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        if hours > 0
        else f"{minutes:02d}:{seconds:02d}"
    )

class NovelTranslator:
    """
    Class encapsulating the novel translation logic with detailed logging.
    """
    def __init__(self, service: str, novel_id: str):
        self.service = service
        self.novel_id = novel_id
        self.api_key = self._load_api_key()
        self.api_config = config.API_CONFIG[service]
        self.session = self._create_age_verified_session()
        self.prompt_template_content = None # Will be loaded for each chapter

    def _get_novel_directory(self) -> str:
        dir_name = f"{config.NOVEL_DIR_PREFIX}{self.novel_id}"
        os.makedirs(dir_name, exist_ok=True)
        return dir_name

    def _load_api_key(self) -> str:
        filename = f'api_key_{self.service}.txt'
        try:
            with open(filename, 'r', encoding='utf-8-sig') as f:
                key = f.read().strip()
                if not key: raise ValueError("API key file is empty.")
                log_message(f"API key loaded for {self.service}.")
                return key
        except (FileNotFoundError, ValueError) as e:
            log_message(f"Error: {e}. Please create/check {filename} with your API key.")
            sys.exit(1)

    def _create_age_verified_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        })
        session.cookies.set('over18', 'yes', domain='.syosetu.com')
        return session

    def _load_prompt_template(self) -> str:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.join(script_dir, 'prompt_template.txt')
        try:
            with open(template_path, 'r', encoding='utf-8-sig') as f:
                content = f.read()
            token_estimate = estimate_tokens(content)
            log_message(f"Prompt template loaded: {len(content)} characters, ~{token_estimate} tokens")
            return content
        except FileNotFoundError:
            log_message(f"Error: Prompt template not found at {template_path}")
            sys.exit(1)

    def get_chapter_content(self, url: str) -> str:
        log_message(f"Fetching chapter content from: {url}")
        try:
            log_message("Fetching content with age verification cookie...")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            response.encoding = 'utf-8'
            if "年齢確認" in response.text:
                log_message("Warning: Age verification page was detected despite bypass.")

            # Instead of extracting text, convert to Markdown
            markdown_content = self._convert_chapter_to_markdown(response.text)
            token_estimate = estimate_tokens(markdown_content)
            log_message(f"Converted to Markdown: {len(markdown_content)} characters, ~{token_estimate} tokens")
            return markdown_content

        except requests.exceptions.RequestException as e:
            log_message(f"Fatal: Error fetching URL content: {e}")
            return ""

    def _process_ruby_tags(self, soup):
        """Processes ruby tags to convert to text format"""
        for ruby in soup.find_all('ruby'):
            rb = ruby.find('rb') or ruby.find_next(string=True)
            rt = ruby.find('rt')
            
            if rb and rt:
                rb_text = rb.get_text(strip=True) if hasattr(rb, 'get_text') else rb.strip()
                rt_text = rt.get_text(strip=True)
                ruby.replace_with(f"{rb_text}({rt_text})")
        return soup

    def _convert_chapter_to_markdown(self, html_content: str) -> str:
        """Converts syosetu chapter HTML to structured Markdown"""
        # Initialize HTML to Markdown converter
        h2t = html2text.HTML2Text()
        h2t.body_width = 0  # Disable line wrapping
        h2t.ignore_links = False
        h2t.ignore_images = True
        
        # Standard Markdown horizontal rule
        HR = "---\n\n"
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract chapter title (level 2)
        title_tag = soup.find('h1', class_='p-novel__title')
        title = title_tag.get_text(strip=True) if title_tag else "Untitled Chapter"
        markdown_output = f"## {title}\n\n"
        
        # Find chapter body
        body_div = soup.find('div', class_='p-novel__body')
        if not body_div:
            return markdown_output + "> Chapter content not found"
        
        # Process author's preface (level 3)
        preface = body_div.find('div', class_='p-novel__text--preface')
        if preface:
            preface_text = self._process_ruby_tags(preface)
            markdown_output += "### Author's Preface\n\n" + h2t.handle(str(preface_text)) + "\n\n"
            markdown_output += HR  # Horizontal rule after preface
        
        # Process main text
        main_text_divs = []
        for div in body_div.find_all('div', class_='p-novel__text'):
            classes = div.get('class', [])
            if 'p-novel__text--preface' not in classes and 'p-novel__text--afterword' not in classes:
                main_text_divs.append(div)
        
        if main_text_divs:
            main_content = "\n\n".join(str(self._process_ruby_tags(div)) for div in main_text_divs)
            markdown_output += h2t.handle(main_content) + "\n\n"
        
        # Add separator before afterword if main text exists
        if main_text_divs and body_div.find('div', class_='p-novel__text--afterword'):
            markdown_output += HR  # Horizontal rule before afterword
        
        # Process author's afterword (level 3)
        afterword = body_div.find('div', class_='p-novel__text--afterword')
        if afterword:
            afterword_text = self._process_ruby_tags(afterword)
            markdown_output += "### Author's Afterword\n\n" + h2t.handle(str(afterword_text)) + "\n\n"
        
        # Remove extra line breaks
        cleaned_output = re.sub(r'\n{3,}', '\n\n', markdown_output.strip())
        return cleaned_output

    def _load_all_notes(self) -> dict[str, str]:
        """Loads all note files into a dictionary using config templates."""
        dir_name = self._get_novel_directory()
        loaded_notes = {}
        total_tokens = 0
        log_message("Loading all note files...")
        for key, filename_template in config.NOTE_FILE_TEMPLATES.items():
            filename = filename_template.format(novel_id=self.novel_id)
            path = os.path.join(dir_name, filename)
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    loaded_notes[key] = content
                    tokens = estimate_tokens(content)
                    total_tokens += tokens
                    log_message(f"  - Loaded '{filename}': {len(content)} chars, ~{tokens} tokens")
            else:
                loaded_notes[key] = ""
                log_message(f"  - File not found, using empty content for '{filename}'")
        log_message(f"Total notes loaded: ~{total_tokens} tokens")
        return loaded_notes

    def _build_prompt(self, chapter_content: str, all_notes: dict[str, str]) -> str:
        # Combine all notes into a single block for the prompt
        combined_notes = (
            f"{all_notes.get('static', '')}\n\n"
            f"{all_notes.get('chars', '')}\n\n"
            f"{all_notes.get('terms', '')}\n\n"
            f"{all_notes.get('chapter_specific', '')}"
        ).strip()

        prompt = self.prompt_template_content.replace("{{chapter_content}}", chapter_content)
        prompt = prompt.replace("{{fixed_notes}}", combined_notes)
        prompt = prompt.replace("{{translation_notes}}", "# No running notes used in this new workflow.")

        prompt_tokens = estimate_tokens(prompt)
        log_message(f"Final prompt size: {len(prompt)} characters, ~{prompt_tokens} tokens")
        return prompt

    def _send_request_to_llm(self, prompt: str) -> str | None:
        """Makes a single, interruptible API call attempt."""
        payload = {"model": self.api_config["model"], "messages": [{"role": "user", "content": prompt}], "temperature": config.DEFAULT_TEMPERATURE, "stream": False}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        
        response_data = {"content": None, "error": None, "status_code": None, "raw_text": None}

        def worker():
            try:
                response = requests.post(
                    self.api_config["url"],
                    headers=headers,
                    data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                    timeout=config.REQUEST_TIMEOUT_SECONDS
                )
                response_data["status_code"] = response.status_code
                if response.status_code == 200:
                    response_data["content"] = response.json()['choices'][0]['message']['content']
                else:
                    response_data["raw_text"] = response.text[:200]
            except Exception as e:
                response_data["error"] = e

        request_thread = threading.Thread(target=worker)
        request_thread.daemon = True
        
        log_message("Translation in progress... Press Ctrl+C to interrupt.")
        request_start_time = time.time()
        request_thread.start()

        try:
            while request_thread.is_alive():
                request_thread.join(0.5)
        except KeyboardInterrupt:
            log_message("\nTranslation interrupted by user. Exiting.")
            sys.exit(0)

        if response_data["error"]:
            log_message(f"API request failed: {response_data['error']}")
            return None

        if response_data["status_code"] != 200:
            log_message(f"Error: API returned status {response_data['status_code']}: {response_data['raw_text']}")
            return None
        
        elapsed = time.time() - request_start_time
        log_message(f"Translation received in {format_duration(elapsed)}")
        content = response_data["content"]
        response_tokens = estimate_tokens(content)
        tps = response_tokens / elapsed if elapsed > 0 else 0
        log_message(f"Response size: {len(content)} chars, ~{response_tokens} tokens. TPS: {tps:.2f}")
        return content

    def _parse_llm_response(self, cleaned_content: str) -> tuple[str, str]:
        """Parses the response cleaned of <think> blocks, splitting into notes and markdown."""
        try:
            _, notes_and_html = cleaned_content.split(config.NOTES_MARKER, 1)
            notes, html_block = notes_and_html.split(config.MD_TRANSLATION_MARKER, 1)
            
            # Remove initial code block with possible spaces and newlines
            html_block = re.sub(r'^(\s*```\s*markdown\s*\n?)', '', html_block, flags=re.IGNORECASE)
            
            # Find position of translation marker
            marker_pos = html_block.find(config.CHAPTER_TRANSLATION_NOTES_MARKER)
            if marker_pos != -1:
                # Find first non-whitespace character before the marker
                prev_char_pos = marker_pos - 1
                while prev_char_pos >= 0 and html_block[prev_char_pos].isspace():
                    prev_char_pos -= 1
                
                # If there's a code block before whitespace
                if prev_char_pos >= 2 and html_block[prev_char_pos-2:prev_char_pos+1] == '```':
                    # Remove code block and all whitespace after it
                    # Save part before the code block
                    part_before = html_block[:prev_char_pos-2]
                    
                    # Leave exactly 2 newlines before marker
                    html_block = part_before + "\n\n" + config.CHAPTER_TRANSLATION_NOTES_MARKER
                    
                    # Add remaining part after marker
                    if marker_pos + len(config.CHAPTER_TRANSLATION_NOTES_MARKER) < len(html_block):
                        html_block += html_block[marker_pos + len(config.CHAPTER_TRANSLATION_NOTES_MARKER):]
                    
                    log_message("Removed closing code block before translation notes marker")

            # Remove trailing code block (only at very end of file)
            html_block = re.sub(r'\n?\s*```\s*$', '', html_block, flags=re.IGNORECASE)
            
            html = html_block.strip()
            
            return notes.strip(), html
        except ValueError:
            log_message("Fatal: Could not parse LLM response with standard markers. Check LLM output.")
            return "Could not extract notes.", cleaned_content

    def _validate_response_structure(self, response_content: str) -> tuple[bool, list[str]]:
        """Checks for presence and order of key headers in LLM response."""
        messages = []
        
        # 1. Find position of NOTES_MARKER
        pos1 = response_content.find(config.NOTES_MARKER)
        if pos1 == -1:
            messages.append(f"Validation FAIL: Missing marker '{config.NOTES_MARKER}'")
            return False, messages

        # 2. Find position of chapter_specific pattern
        chapter_specific_pattern = config.NOTE_SECTION_PATTERNS["chapter_specific"]
        # FIX: Added re.DOTALL flag so '.' matches newline
        match = re.search(chapter_specific_pattern, response_content, re.IGNORECASE | re.DOTALL)
        if not match:
            messages.append(f"Validation FAIL: Missing pattern for 'Chapter-specific Notes'")
            return False, messages
        pos2 = match.start()

        # 3. Find position of MD_TRANSLATION_MARKER
        pos3 = response_content.find(config.MD_TRANSLATION_MARKER)
        if pos3 == -1:
            messages.append(f"Validation FAIL: Missing marker '{config.MD_TRANSLATION_MARKER}'")
            return False, messages
        
        # 4. Find position of CHAPTER_TRANSLATION_NOTES_MARKER
        pos4 = response_content.find(config.CHAPTER_TRANSLATION_NOTES_MARKER)
        if pos4 == -1:
            messages.append(f"Validation FAIL: Missing marker '{config.CHAPTER_TRANSLATION_NOTES_MARKER}'")
            return False, messages

        # Check order
        if not (pos1 < pos2 < pos3 < pos4):
             messages.append(f"Validation FAIL: Markers are out of order. "
                           f"Order found: NOTES ({pos1}), CHAPTER_SPECIFIC ({pos2}), "
                           f"MD_TRANSLATION ({pos3}), TRANSLATION_NOTES ({pos4})")
             return False, messages
        
        messages.append("Response structure OK: All required markers found in the correct order.")
        return True, messages

    def _validate_response_size(self, html: str, original_content: str) -> tuple[bool, list[str]]:
        """Validates that translation size (excluding Chapter Translation Notes section) is within acceptable limits."""
        is_valid = True
        messages = []
        
        # Exclude Chapter Translation Notes section from length calculation
        notes_marker_pos = html.find(config.CHAPTER_TRANSLATION_NOTES_MARKER)
        if notes_marker_pos != -1:
            translation_part = html[:notes_marker_pos].strip()
            messages.append(f"Excluded Chapter Translation Notes section from size calculation.")
        else:
            translation_part = html
            messages.append(f"Chapter Translation Notes section not found. Using entire response for size check.")
        
        # Clean text from markup and normalize whitespace
        cleaned_translation = self._clean_text_for_size_check(translation_part)
        cleaned_original = self._clean_text_for_size_check(original_content)
        
        translation_len = len(cleaned_translation)
        original_clean_len = len(cleaned_original)
        
        # Calculate actual ratio
        actual_ratio = translation_len / original_clean_len if original_clean_len > 0 else 0
        ratio_percent = f"{actual_ratio:.2f}x"
    
        # Base values from config
        min_ratio = config.TRANSLATION_SIZE_MIN_RATIO
        max_ratio = config.TRANSLATION_SIZE_MAX_RATIO
                    
        min_expected = round(original_clean_len * min_ratio)
        max_expected = round(original_clean_len * max_ratio)
    
        if not (min_expected <= translation_len <= max_expected):
            messages.append(f"WARNING: Clean text size mismatch: {translation_len} chars (ratio {ratio_percent}, expected {min_expected}-{max_expected} [{min_ratio:.2f}x-{max_ratio:.2f}x])")
            is_valid = False
        else:
            messages.append(f"Clean text size OK: {translation_len} chars (ratio {ratio_percent}, within {min_expected}-{max_expected} [{min_ratio:.2f}x-{max_ratio:.2f}x])")
        
        # Add full length info for debugging
        if notes_marker_pos != -1:
            messages.append(f"Full response size: {len(html)} chars (including notes)")
            messages.append(f"Original clean text size: {original_clean_len} chars")
        
        return is_valid, messages

    def _clean_text_for_size_check(self, text: str) -> str:
        """Cleans text from Markdown markup and normalizes whitespace for size validation."""
        # Remove Markdown markup
        cleaned = re.sub(
            r'(#+\s*)|([*_]{1,3})|(\!?\[.*?\]\(.*?\))|(`{1,3}.*?`{1,3})|(^\s*[-*+]\s*)|(^\s*\d+\.\s*)|(\|.*?\|)|(---+)',
            ' ',
            text,
            flags=re.MULTILINE | re.DOTALL
        )
        
        # Replace HTML entities
        cleaned = html_escape.unescape(cleaned)
        
        # Replace all sequences of spaces and newlines with single space
        cleaned = re.sub(r'\s+', ' ', cleaned)
        
        # Remove leading/trailing spaces
        return cleaned.strip()

    def _parse_new_notes_from_llm(self, llm_notes_section: str) -> dict[str, str]:
        notes = { "characters": "", "terms": "", "chapter_specific": "" }
        for key, pattern in config.NOTE_SECTION_PATTERNS.items():
            match = re.search(pattern, llm_notes_section, re.DOTALL | re.IGNORECASE)
            if match:
                content = match.group(1).strip()
                # Remove possible trailing backticks in section
                clean_content = re.sub(r'`+$', '', content)
                notes[key] = clean_content
        return notes

    def _get_updated_notes_content(self, current_notes: dict, new_notes: dict, part_num: str) -> dict[str, str]:
        """Prepares updated content for note files."""
        updated_content = {}
        
        # 1. Update Character Names (append to end)
        new_characters = new_notes.get("characters", "").strip()
        skip_chars = new_characters.lower() in config.NOTES_SKIP_PHRASES or not new_characters
        
        current_chars_content = current_notes.get('chars', '')
        if not skip_chars and new_characters in current_chars_content:
            skip_chars = True
            log_message(f"Skipping duplicate character name: '{new_characters}'")
        
        updated_chars = current_chars_content
        if new_characters and not skip_chars:
            if updated_chars.strip():
                updated_chars += '\n'
            updated_chars += new_characters
            log_message("Prepared updated content for character names.")
        elif skip_chars:
            log_message("Skipping character names update - no new entries")
        updated_content['chars'] = updated_chars
    
        # 2. Update Special Terms (append to end)
        new_terms = new_notes.get("terms", "").strip()
        skip_terms = new_terms.lower() in config.NOTES_SKIP_PHRASES or not new_terms

        current_terms_content = current_notes.get('terms', '')
        if not skip_terms and new_terms in current_terms_content:
            skip_terms = True
            log_message(f"Skipping duplicate special term: '{new_terms}'")
        
        updated_terms = current_terms_content
        if new_terms and not skip_terms:
            if updated_terms.strip():
                updated_terms += '\n'
            updated_terms += new_terms
            log_message("Prepared updated content for special terms.")
        elif skip_terms:
            log_message("Skipping special terms update - no new entries")
        updated_content['terms'] = updated_terms
        
        # 3. Update Chapter-specific Notes (prepend and truncate)
        new_chapter_specific = new_notes.get("chapter_specific", "").strip()
        updated_chapter_notes = current_notes.get('chapter_specific', '')
        
        if new_chapter_specific and new_chapter_specific.lower() not in config.NOTES_SKIP_PHRASES:
            existing_notes_text = re.sub(r'^{}\n?'.format(re.escape(config.CHAPTER_SPECIFIC_NOTES_HEADER)), '', updated_chapter_notes).strip()
            
            full_content = f"{new_chapter_specific}\n\n{existing_notes_text}" if existing_notes_text else new_chapter_specific
            
            lines = full_content.split('\n')
            if len(lines) > config.MAX_CHAPTER_SPECIFIC_NOTE_LINES:
                lines = lines[:config.MAX_CHAPTER_SPECIFIC_NOTE_LINES]
                log_message(f"Chapter-specific notes truncated to {config.MAX_CHAPTER_SPECIFIC_NOTE_LINES} lines.")
            
            updated_content['chapter_specific'] = (
                f"{config.CHAPTER_SPECIFIC_NOTES_HEADER}\n" +
                "\n".join(lines).strip()
            )
            log_message("Prepared updated content for chapter-specific notes.")
        else:
            if new_chapter_specific.lower() in config.NOTES_SKIP_PHRASES:
                log_message("Skipping chapter-specific notes update - no new entries")
            updated_content['chapter_specific'] = updated_chapter_notes
            
        return updated_content

    def _save_final_files(self, part_num: str, markdown_content: str, updated_notes: dict):
        dir_name = self._get_novel_directory()

        # Save 3 updatable note files
        for note_key, content in updated_notes.items():
            if content: # Save only if content exists
                filename_template = config.NOTE_FILE_TEMPLATES.get(note_key)
                if filename_template:
                    filename = filename_template.format(novel_id=self.novel_id)
                    path = os.path.join(dir_name, filename)
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    log_message(f"Updated notes file saved: {path}")

        # Save translated .md file
        formatted_part_num = part_num.zfill(3)
        final_md_filename = config.TRANSLATED_FILENAME_TEMPLATE.format(
            novel_id=self.novel_id,
            part_num=formatted_part_num
        )
        final_md_path = os.path.join(dir_name, final_md_filename)
        with open(final_md_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        log_message(f"Translated chapter saved to: {final_md_path}")

        # Apply fixes to Markdown file
        log_message(f"Applying markdown fixes to {final_md_path}...")
        try:
            process_md_file(Path(final_md_path), Path(final_md_path))
            log_message("Markdown fixes applied successfully.")
        except Exception as e:
            log_message(f"Error applying markdown fixes: {e}")


    def _create_backup(self, part_num: str, original_content: str, notes_before: dict, llm_response: str, final_translation: str, final_prompt: str, is_failure: bool = False):
        """Creates a full backup including all note files and scripts."""
        dir_name = self._get_novel_directory()
        timestamp = datetime.now().strftime(config.BACKUP_TIMESTAMP_FORMAT)
        
        backup_dir_name = config.BACKUP_DIR_TEMPLATE.format(timestamp=timestamp, part_num=part_num.zfill(3))
        if is_failure:
            backup_dir_name += "_Validation_FAIL"
        
        backup_path = os.path.join(dir_name, config.BACKUPS_SUBDIR, backup_dir_name)
        
        os.makedirs(backup_path, exist_ok=True)
        log_message(f"Creating {'failure ' if is_failure else ''}backup in: {backup_path}")
    
        # Copy script files to backup
        backed_up_scripts = []
        for script_name in config.SCRIPTS_TO_BACKUP:
            src_path = os.path.join(os.path.dirname(__file__), script_name)
            if os.path.exists(src_path):
                shutil.copy2(src_path, os.path.join(backup_path, script_name))
                backed_up_scripts.append(script_name)
            else:
                log_message(f"Warning: Script not found for backup - {script_name}")
        if backed_up_scripts:
            log_message(f"Backed up scripts: {', '.join(backed_up_scripts)}")

        # Collect all text files for backup
        files_to_save_in_backup = {
            config.BACKUP_FILES["prompt_template"]: self.prompt_template_content,
            config.BACKUP_FILES["final_prompt"].format(part_num=part_num.zfill(3)): final_prompt,
            config.BACKUP_FILES["original_chapter"].format(part_num=part_num.zfill(3)): original_content,
            config.BACKUP_FILES["llm_response"].format(part_num=part_num.zfill(3)): llm_response,
            config.BACKUP_FILES["translation"].format(part_num=part_num.zfill(3)): final_translation,
        }
    
        # Add note files (that existed before translation)
        for note_key, content in notes_before.items():
            if content: # Backup only non-empty note files
                filename_template = config.NOTE_FILE_TEMPLATES.get(note_key)
                if filename_template:
                    filename = filename_template.format(novel_id=self.novel_id)
                    files_to_save_in_backup[f"{filename}"] = content

        for filename, content in files_to_save_in_backup.items():
            try:
                with open(os.path.join(backup_path, filename), 'w', encoding='utf-8') as f:
                    f.write(content)
            except Exception as e:
                log_message(f"Error writing backup file {filename}: {e}")

    def translate_chapter(self, chapter_url: str):
        part_num_match = re.search(r'/(\d+)/?$', chapter_url)
        if not part_num_match:
            log_message(f"Could not extract chapter number from URL: {chapter_url}")
            return
        part_num = part_num_match.group(1)

        log_message(f"\n{'='*50}\nProcessing Part {part_num}...")
        
        self.prompt_template_content = self._load_prompt_template()

        original_content = ""
        for fetch_attempt in range(1, config.MAX_TRANSLATION_ATTEMPTS + 1):
            original_content = self.get_chapter_content(chapter_url)
            if original_content: break
            if fetch_attempt < config.MAX_TRANSLATION_ATTEMPTS:
                log_message(f"Fetch failed, retrying... ({fetch_attempt})")
                time.sleep(config.GENERAL_DELAY_SECONDS)
            else:
                log_message("FATAL: Max fetch attempts reached. Stopping chapter.")
                return

        notes_before_update = self._load_all_notes()
        prompt = self._build_prompt(original_content, notes_before_update)
        
        for attempt in range(1, config.MAX_TRANSLATION_ATTEMPTS + 1):
            log_message(f"Translation and validation attempt {attempt}/{config.MAX_TRANSLATION_ATTEMPTS}...")
            
            raw_llm_response = self._send_request_to_llm(prompt)
            if not raw_llm_response:
                log_message("API request failed.")
                if attempt < config.MAX_TRANSLATION_ATTEMPTS:
                    log_message("Retrying after a delay...")
                    time.sleep(config.GENERAL_DELAY_SECONDS)
                continue

            cleaned_llm_response = re.sub(config.THINK_BLOCK_PATTERN, '', raw_llm_response, flags=re.DOTALL)
            if len(raw_llm_response) != len(cleaned_llm_response):
                log_message("Removed <think> blocks from API response")

            # 1. Validate response structure
            is_struct_valid, struct_messages = self._validate_response_structure(cleaned_llm_response)
            for msg in struct_messages: log_message(msg)

            if not is_struct_valid:
                log_message("Translation failed structure validation.")
                self._create_backup(
                    part_num, original_content, notes_before_update, 
                    raw_llm_response, cleaned_llm_response, prompt, is_failure=True
                )
                if attempt < config.MAX_TRANSLATION_ATTEMPTS:
                    log_message("Retrying after a delay...")
                    time.sleep(config.GENERAL_DELAY_SECONDS)
                continue

            # If structure is valid, parse response
            llm_notes, translated_md = self._parse_llm_response(cleaned_llm_response)
            
            # Check if parser returned original text (error sign)
            if translated_md == cleaned_llm_response:
                log_message("Translation failed validation (parsing error).")
                self._create_backup(
                    part_num, original_content, notes_before_update, 
                    raw_llm_response, cleaned_llm_response, prompt, is_failure=True
                )
                if attempt < config.MAX_TRANSLATION_ATTEMPTS:
                    log_message("Retrying after a delay...")
                    time.sleep(config.GENERAL_DELAY_SECONDS)
                continue

            # 2. Validate translation size
            is_size_valid, size_messages = self._validate_response_size(translated_md, original_content)  # Pass original content
            for msg in size_messages: log_message(msg)

            if is_size_valid:
                final_md = html_escape.unescape(translated_md)
                new_notes_data = self._parse_new_notes_from_llm(llm_notes)
                updated_notes_content = self._get_updated_notes_content(notes_before_update, new_notes_data, part_num)
                self._save_final_files(part_num, final_md, updated_notes_content)
                self._create_backup(
                    part_num, original_content, notes_before_update, 
                    raw_llm_response, final_md, prompt
                )
                return 

            log_message("Translation failed size validation.")
            self._create_backup(
                part_num, original_content, notes_before_update, 
                raw_llm_response, translated_md, prompt, is_failure=True
            )
            if attempt < config.MAX_TRANSLATION_ATTEMPTS:
                log_message("Retrying after a delay...")
                time.sleep(config.GENERAL_DELAY_SECONDS)
        
        log_message(f"FATAL: Max {config.MAX_TRANSLATION_ATTEMPTS} attempts reached. Failed to get a valid translation for this chapter.")


# --- Command line functions (unchanged) ---
def extract_novel_id_from_url(url: str) -> str:
    match = re.search(r'/(n[a-z0-9]+)/', url)
    return match.group(1) if match else "unknown_novel"

def main():
    setup_encoding()
    if sys.platform == "win32":
        os.system("chcp 65001 > nul")

    parser = argparse.ArgumentParser(description='Translate syosetu novel chapters using LLM.')
    parser.add_argument('url', help='Base URL of the chapter or novel series.')
    parser.add_argument('range', nargs='?', help='Optional chapter range, e.g., "10-15" or "12-14,17-30".')
    parser.add_argument('--service', '-s', default='chutes', choices=config.API_CONFIG.keys(), help='API service to use.')
    args = parser.parse_args()

    novel_id = extract_novel_id_from_url(args.url)
    translator = NovelTranslator(service=args.service, novel_id=novel_id)

    if args.range:
        chapter_list = []
        base_url = re.sub(r'/\d+/?$', '', args.url.rstrip('/'))
        range_parts = args.range.split(',')
        for part in range_parts:
            if '-' in part:
                try:
                    start_str, end_str = part.split('-')
                    chapter_list.extend(range(int(start_str), int(end_str) + 1))
                except ValueError:
                    log_message(f"Error: Invalid range format in '{part}'.")
            else:
                try:
                    chapter_list.append(int(part))
                except ValueError:
                    log_message(f"Error: Invalid chapter number '{part}'.")
        
        chapter_list = sorted(set(chapter_list))
        if not chapter_list:
            log_message("Error: No valid chapters specified.")
            sys.exit(1)
        
        for i, ch in enumerate(chapter_list):
            chapter_url = f"{base_url}/{ch}/"
            translator.translate_chapter(chapter_url)
            if i < len(chapter_list) - 1:
                log_message(f"Waiting {config.GENERAL_DELAY_SECONDS} seconds before next chapter...")
                time.sleep(config.GENERAL_DELAY_SECONDS)
    else:
        translator.translate_chapter(args.url)
    
    log_message("\nTranslation process completed.")

if __name__ == "__main__":
    main()