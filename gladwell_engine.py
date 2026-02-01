"""
Un:Curve Weekly Newsletter Engine
Generates Malcolm Gladwell-style newsletters using DeepSeek Reasoner API.
Publishes to Make.com webhook for Brevo email distribution.

Usage:
    python gladwell_engine.py    # Generate weekly newsletter and publish to webhook
"""

import os
import sys
import re
import json
import time
import random
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from duckduckgo_search import DDGS
from openai import OpenAI

# Load environment variables
load_dotenv()

# Configuration
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL")

BASE_DIR = Path(__file__).parent
SYSTEM_PROMPT_PATH = BASE_DIR / "config" / "GLADWELL_NEWSLETTER_SYSTEM.md"
DRAFTS_DIR = BASE_DIR / "drafts"
EMAIL_TEMPLATE_PATH = BASE_DIR / "templates" / "email_template.html"
HISTORY_FILE = BASE_DIR / "headline_history.json"

# Ensure drafts directory exists
DRAFTS_DIR.mkdir(exist_ok=True)


def load_system_prompt() -> str:
    """Load the Gladwell Newsletter System prompt."""
    with open(SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


def load_email_template() -> str:
    """Load the HTML email template."""
    with open(EMAIL_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        return f.read()


def load_headline_history() -> list[str]:
    """Load previously used headline URLs to avoid duplicates."""
    if not HISTORY_FILE.exists():
        return []
    
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("used_urls", [])
    except (json.JSONDecodeError, Exception):
        return []


def save_headline_to_history(url: str, title: str, topic: str = ""):
    """Save a used headline to history to prevent future duplicates."""
    full_history = []
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                full_history = data.get("headlines", [])
        except:
            pass
    
    full_history.append({
        "url": url,
        "title": title,
        "topic": topic,
        "date": datetime.now().strftime("%Y-%m-%d")
    })
    
    # Keep only last 100 headlines
    full_history = full_history[-100:]
    history = [h["url"] for h in full_history]
    
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "used_urls": history,
            "headlines": full_history
        }, f, indent=2)
    
    print(f"[HISTORY] Saved headline to history ({len(history)} total, topic: {topic})")


def filter_used_headlines(headlines: list[dict]) -> list[dict]:
    """Remove headlines that have already been used."""
    used_urls = load_headline_history()
    
    filtered = []
    for h in headlines:
        if h.get("url") not in used_urls:
            filtered.append(h)
    
    removed = len(headlines) - len(filtered)
    if removed > 0:
        print(f"[HISTORY] Filtered out {removed} previously used headline(s)")
    
    return filtered


def get_recent_topics(count: int = 5) -> list[str]:
    """Get the topic areas from the last N newsletters to avoid repetition."""
    if not HISTORY_FILE.exists():
        return []
    
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            headlines = data.get("headlines", [])
            recent_topics = [h.get("topic", "") for h in headlines[-count:] if h.get("topic")]
            return recent_topics
    except:
        return []


def scout_headlines(num_results: int = 10) -> list[dict]:
    """PHASE 1: SCOUT - Search the web for anomalous headlines."""
    print("[SCOUT] Searching for anomalous headlines...")
    
    all_queries = [
        "surprising research findings 2026",
        "study contradicts conventional wisdom",
        "counter-intuitive study results",
        "research challenges assumptions",
        "behavioral economics surprising",
        "psychology study unexpected results",
        "decision making research new",
        "business paradox research",
        "success failure paradox study",
        "economics counter-intuitive",
        "sociology surprising discovery",
        "cultural study unexpected",
        "criminology new findings",
        "unintended consequences research",
        "policy backfire study",
    ]
    
    queries = random.sample(all_queries, min(5, len(all_queries)))
    all_results = []
    
    with DDGS() as ddgs:
        for i, query in enumerate(queries):
            try:
                if i > 0:
                    time.sleep(1.5)
                results = list(ddgs.news(query, max_results=4))
                all_results.extend(results)
                print(f"  Found {len(results)} results for: {query[:40]}...")
            except Exception as e:
                print(f"  Warning: Search failed for '{query}': {e}")
                time.sleep(2)
                continue
    
    seen_titles = set()
    unique_results = []
    for r in all_results:
        if r.get("title") not in seen_titles:
            seen_titles.add(r.get("title"))
            unique_results.append({
                "title": r.get("title", ""),
                "body": r.get("body", ""),
                "url": r.get("url", ""),
                "source": r.get("source", ""),
            })
    
    print(f"[SCOUT] Found {len(unique_results)} unique headlines.")
    
    unique_results = filter_used_headlines(unique_results)
    
    if not unique_results:
        print("[SCOUT] WARNING: All headlines have been used. Consider expanding search queries.")
    
    return unique_results[:num_results]


def braider_select(client: OpenAI, system_prompt: str, headlines: list[dict]) -> dict:
    """PHASE 2: BRAIDER - Select best headline and choose template."""
    print("[BRAIDER] Analyzing headlines for Davis pattern violations...")
    
    recent_topics = get_recent_topics(5)
    topics_to_avoid = ""
    if recent_topics:
        topics_to_avoid = f"\n\nTOPIC DIVERSITY REQUIREMENT:\nThe following topic areas have been covered in recent newsletters. DO NOT select a headline in these areas:\n- " + "\n- ".join(recent_topics) + "\n\nChoose a headline from a DIFFERENT topic area to ensure variety."
        print(f"[BRAIDER] Avoiding topics: {recent_topics}")
    
    headlines_text = "\n\n".join([
        f"[{i+1}] {h['title']}\n    Source: {h['source']}\n    Snippet: {h['body']}\n    URL: {h['url']}"
        for i, h in enumerate(headlines)
    ])
    
    selection_prompt = f"""You are a newsletter editor using the Gladwell system.

HEADLINES TO EVALUATE:
{headlines_text}
{topics_to_avoid}

YOUR TASK:
1. Evaluate each headline against the Davis Index.
2. REJECT any headline that confirms conventional wisdom.
3. REJECT any headline covering a topic area listed above (if any).
4. SELECT the single most Gladwellian headline from a FRESH topic area.
5. Identify which Davis Pattern it violates (D1-D10).
6. Choose the appropriate Template (1-6).
7. Identify the broad topic area (e.g., "autism research", "behavioral economics", "urban planning", "education policy").

OUTPUT FORMAT (JSON):
{{
    "selected_headline_number": <1-{len(headlines)}>,
    "headline_title": "<exact title>",
    "headline_url": "<url>",
    "topic_area": "<broad topic category, 2-3 words>",
    "davis_pattern": "<D1-D10>",
    "davis_explanation": "<one sentence>",
    "template_number": <1-6>,
    "template_name": "<template name>",
    "research_needs": "<what additional research is needed>"
}}

Respond ONLY with valid JSON."""

    response = client.chat.completions.create(
        model="deepseek-reasoner",
        messages=[
            {"role": "system", "content": "You are a newsletter editor. Respond only with valid JSON."},
            {"role": "user", "content": selection_prompt}
        ],
        temperature=0.3,
    )
    
    try:
        result = json.loads(response.choices[0].message.content)
        print(f"[BRAIDER] Selected: {result.get('headline_title', 'Unknown')}")
        print(f"[BRAIDER] Davis Pattern: {result.get('davis_pattern', 'Unknown')}")
        return result
    except json.JSONDecodeError:
        print("[BRAIDER] Warning: Could not parse response as JSON.")
        return {"raw_response": response.choices[0].message.content}


def get_newsletter_config() -> dict:
    """Get newsletter configuration for weekly edition."""
    return {
        "type": "Weekly Deep Dive",
        "length": "1200-1500 words",
        "templates": "1, 2, or 3 (prefer complex braids)",
        "style": "Take your time. Build the narrative slowly. Use more historical parallels."
    }


def writer_generate(client: OpenAI, system_prompt: str, selection: dict) -> str:
    """PHASE 3: WRITER - Generate the full newsletter."""
    print("[WRITER] Generating newsletter draft...")
    
    config = get_newsletter_config()
    print(f"[WRITER] Mode: {config['type']} ({config['length']})")
    
    writer_prompt = f"""You are writing a Gladwell-style newsletter.

NEWSLETTER TYPE: {config['type']}
TARGET LENGTH: {config['length']}
STYLE GUIDANCE: {config['style']}

SELECTED HEADLINE:
Title: {selection.get('headline_title', 'Unknown')}
URL: {selection.get('headline_url', 'Unknown')}
Davis Pattern: {selection.get('davis_pattern', 'Unknown')} - {selection.get('davis_explanation', '')}
Template: Template {selection.get('template_number', 5)} ({selection.get('template_name', 'Deep Dive')})

⚠️ NONFICTION REQUIREMENTS (CRITICAL):
- EVERY study, statistic, quote, and person you mention MUST be real and verifiable.
- If you are not 100% certain a study exists, DO NOT cite it. Use general language instead.
- NEVER invent study names, author names, or specific statistics.
- If unsure, say "research suggests..." instead of "A 2019 study by Smith found..."
- Attribute real sources: "According to research published in..." or "As [real person] noted..."

CRITICAL FORMATTING RULES:
- **ABSOLUTELY NO HEADERS** (no ##, no bold section titles). The narrative must flow through prose alone.
- **ABSOLUTELY NO BULLET LISTS**. Convert any list-like content into flowing sentences.
- **ABSOLUTELY NO NUMBERED LISTS** except in References.
- Use ONLY: paragraphs, italics for emphasis, footnotes, and section breaks (use * on its own line).

GLADWELL NARRATIVE REQUIREMENTS:
- Open with a SPECIFIC PERSON in a SPECIFIC MOMENT (the "Human Container")
- Braid between anecdote and theory—never stay in one mode too long
- Use pivot phrases: "But here's the problem..." / "It turns out..." / "And then something strange happened."
- Include ONE "reader engagement game" (thought experiment, puzzle, or "what would you do?")
- Return to your opening anecdote at the end, now illuminated by the theory

INSTRUCTIONS:
1. Follow the GLADWELL_NEWSLETTER_SYSTEM exactly.
2. Use Template {selection.get('template_number', 5)} structure.
3. All anecdotes, quotes, and data MUST be real and sourced—DO NOT FABRICATE.
4. Include 2-4 discursive footnotes using [^1] syntax.
5. End with a References section (this is the ONLY place for a header).
6. Target length: {config['length']}.
7. Start with a compelling SUBJECT LINE (prefix with "SUBJECT LINE:").

Write the complete newsletter now. Remember: NO HEADERS, NO LISTS, PURE NARRATIVE PROSE, NO FABRICATION."""

    response = client.chat.completions.create(
        model="deepseek-reasoner",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": writer_prompt}
        ],
        temperature=0.7,
        max_tokens=3000,
    )
    
    newsletter = response.choices[0].message.content
    print(f"[WRITER] Generated {len(newsletter.split())} words.")
    return newsletter


def save_draft(newsletter: str, selection: dict) -> Path:
    """PHASE 4: OUTPUT - Save the newsletter draft."""
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"{today}_newsletter.md"
    filepath = DRAFTS_DIR / filename
    
    metadata = f"""---
date: {today}
headline: {selection.get('headline_title', 'Unknown')}
davis_pattern: {selection.get('davis_pattern', 'Unknown')}
template: {selection.get('template_number', 'Unknown')}
source_url: {selection.get('headline_url', 'Unknown')}
status: published
---

"""
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(metadata + newsletter)
    
    print(f"[OUTPUT] Saved draft to: {filepath}")
    return filepath


def parse_newsletter(content: str) -> dict:
    """Parse newsletter content into components."""
    subject_match = re.search(r'\*\*SUBJECT LINE[:\s]*(.+?)\*\*', content, re.IGNORECASE)
    if not subject_match:
        subject_match = re.search(r'SUBJECT LINE[:\s]*(.+?)[\n\r]', content, re.IGNORECASE)
    
    subject = subject_match.group(1).strip() if subject_match else "The Gladwell Perspective"
    
    content = re.sub(r'^---[\s\S]*?---\s*', '', content)
    
    footnotes_match = re.search(r'\[\^1\]:', content)
    references_match = re.search(r'\*\*References?:\*\*|^References?:', content, re.MULTILINE | re.IGNORECASE)
    
    main_content = content
    footnotes = ""
    references = ""
    
    if references_match:
        split_pos = references_match.start()
        references = content[split_pos:]
        main_content = content[:split_pos]
    
    if footnotes_match:
        footnote_section = re.findall(r'\[\^\d+\]:.*?(?=\[\^\d+\]:|$)', main_content, re.DOTALL)
        if footnote_section:
            first_footnote = re.search(r'\[\^1\]:', main_content)
            if first_footnote:
                footnotes = main_content[first_footnote.start():]
                main_content = main_content[:first_footnote.start()]
    
    return {
        "subject": subject,
        "content": main_content.strip(),
        "footnotes": footnotes.strip(),
        "references": references.strip()
    }


def markdown_to_html(text: str) -> str:
    """Convert markdown to simple HTML."""
    text = re.sub(r'\*\*SUBJECT LINE[:\s]*.+?\*\*\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'SUBJECT LINE[:\s]*.+?[\n\r]', '', text, flags=re.IGNORECASE)
    
    text = re.sub(r'^#{1,6}\s*(.+?)$', r'\1', text, flags=re.MULTILINE)
    
    text = re.sub(r'^\s*[-•]\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s*', '', text, flags=re.MULTILINE)
    
    section_break_html = '<div style="text-align: center; margin: 40px 0; color: #999; letter-spacing: 8px;">• • •</div>'
    text = re.sub(r'^\s*\*\s*$', section_break_html, text, flags=re.MULTILINE)
    text = re.sub(r'^\s*---+\s*$', section_break_html, text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\*\*\*+\s*$', section_break_html, text, flags=re.MULTILINE)
    
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    text = re.sub(r'\[\^(\d+)\](?!:)', r'<sup>\1</sup>', text)
    
    paragraphs = text.split('\n\n')
    processed = []
    for p in paragraphs:
        p = p.strip()
        if p:
            if p.startswith('<div'):
                processed.append(p)
            else:
                processed.append(f'<p>{p}</p>')
    text = ''.join(processed)
    return text


def build_html_email(newsletter: str) -> tuple[str, str]:
    """Build HTML email from newsletter content. Returns (subject, html)."""
    parsed = parse_newsletter(newsletter)
    template = load_email_template()
    
    content_html = markdown_to_html(parsed["content"])
    
    footnotes_html = ""
    if parsed["footnotes"]:
        footnotes = re.findall(r'\[\^(\d+)\]:\s*(.+?)(?=\[\^\d+\]:|$)', parsed["footnotes"], re.DOTALL)
        for num, text in footnotes:
            footnotes_html += f'<p class="footnote"><span class="footnote-marker">[{num}]</span> {text.strip()}</p>'
    
    references_html = ""
    if parsed["references"]:
        refs = parsed["references"].replace("**References:**", "").replace("References:", "").strip()
        ref_lines = [line.strip() for line in refs.split('\n') if line.strip() and line.strip() != '-']
        references_html = "<ul>" + "".join([f"<li>{line.lstrip('- ')}</li>" for line in ref_lines]) + "</ul>"
    
    # Personal note for weekly edition
    personal_note = """
        <p>I hope this week's edition of <strong>Un:Curve</strong> gives you something to chew on. Take some time to reflect on how often the "obvious" answer is actually the wrong one.</p>
        <p>What's one thing you're rethinking after reading this? I'd love to hear from you on X <strong>@anthonycclemons</strong>.</p>
        <p>Have a wonderful week ahead,</p>
        <p>Anthony</p>
        """

    today = datetime.now().strftime("%B %d, %Y")
    html = template.replace("{{SUBJECT}}", parsed["subject"])
    html = html.replace("{{DATE}}", today)
    html = html.replace("{{CONTENT}}", content_html)
    html = html.replace("{{FOOTNOTES}}", footnotes_html if footnotes_html else "<p>No notes for this issue.</p>")
    html = html.replace("{{REFERENCES}}", references_html if references_html else "<p>No references.</p>")
    html = html.replace("{{PERSONAL_NOTE}}", personal_note)
    
    return parsed["subject"], html


def publish_to_webhook(html_content: str, subject: str, metadata: dict) -> bool:
    """Send the final HTML to Make.com webhook for Brevo distribution."""
    if not MAKE_WEBHOOK_URL:
        print("[WEBHOOK] ERROR: MAKE_WEBHOOK_URL not configured")
        return False
    
    payload = {
        "subject": subject,
        "html_content": html_content,
        "send_date": datetime.now().strftime("%Y-%m-%d"),
        "metadata": {
            "headline": metadata.get("headline", ""),
            "davis_pattern": metadata.get("davis_pattern", ""),
            "source_url": metadata.get("source_url", "")
        }
    }
    
    # #region agent log - Check credentials
    webhook_user = os.getenv("MAKE_WEBHOOK_USER")
    webhook_password = os.getenv("MAKE_WEBHOOK_PASSWORD")
    print(f"[DEBUG] MAKE_WEBHOOK_USER set: {bool(webhook_user)}, length: {len(webhook_user) if webhook_user else 0}")
    print(f"[DEBUG] MAKE_WEBHOOK_PASSWORD set: {bool(webhook_password)}, length: {len(webhook_password) if webhook_password else 0}")
    # #endregion
    
    headers = {"Content-Type": "application/json"}
    
    # Make.com uses x-make-apikey header for authentication
    # Try password first (likely the actual API key value), then user
    api_key = webhook_password or webhook_user
    if api_key:
        headers["x-make-apikey"] = api_key
        print(f"[DEBUG] Using x-make-apikey header with key length: {len(api_key)}")
    
    try:
        print(f"[DEBUG] Making POST request to webhook URL (length: {len(MAKE_WEBHOOK_URL)})")
        response = requests.post(MAKE_WEBHOOK_URL, json=payload, headers=headers, timeout=60)
        
        # #region agent log - Log response details
        print(f"[DEBUG] Response status: {response.status_code}")
        if response.status_code != 200:
            print(f"[DEBUG] Response body: {response.text[:500]}")
            # Try the other credential if first one failed
            if response.status_code == 401 and webhook_user and webhook_password:
                print("[DEBUG] First key failed, trying alternate credential...")
                alt_key = webhook_user if api_key == webhook_password else webhook_password
                headers["x-make-apikey"] = alt_key
                print(f"[DEBUG] Trying x-make-apikey with alternate key length: {len(alt_key)}")
                response = requests.post(MAKE_WEBHOOK_URL, json=payload, headers=headers, timeout=60)
                print(f"[DEBUG] Alternate key response status: {response.status_code}")
        # #endregion
        
        response.raise_for_status()
        print(f"[WEBHOOK] Successfully sent to Make.com (status: {response.status_code})")
        return True
    except requests.exceptions.Timeout:
        print("[WEBHOOK] ERROR: Request timed out")
        return False
    except requests.exceptions.RequestException as e:
        print(f"[WEBHOOK] ERROR: {e}")
        return False


def main():
    """Single execution: Generate -> Build HTML -> Push to Make.com"""
    print("=" * 60)
    print("UN:CURVE NEWSLETTER ENGINE")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Validate configuration
    if not DEEPSEEK_API_KEY:
        print("ERROR: DEEPSEEK_API_KEY not configured")
        sys.exit(1)
    
    if not MAKE_WEBHOOK_URL:
        print("ERROR: MAKE_WEBHOOK_URL not configured")
        sys.exit(1)
    
    # Load system prompt
    system_prompt = load_system_prompt()
    print(f"[INIT] Loaded system prompt ({len(system_prompt)} chars)")
    
    # Initialize DeepSeek client
    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    print("[INIT] DeepSeek client initialized")
    
    # PHASE 1: Scout headlines
    headlines = scout_headlines(num_results=10)
    if not headlines:
        print("ERROR: No headlines found")
        sys.exit(1)
    
    # PHASE 2: Select best headline
    selection = braider_select(client, system_prompt, headlines)
    save_headline_to_history(
        selection.get('headline_url', ''),
        selection.get('headline_title', ''),
        selection.get('topic_area', '')
    )
    
    # PHASE 3: Generate newsletter
    newsletter = writer_generate(client, system_prompt, selection)
    
    # PHASE 4: Save draft (for archive)
    draft_path = save_draft(newsletter, selection)
    
    # PHASE 5: Build HTML and push to Make.com
    subject, html = build_html_email(newsletter)
    
    success = publish_to_webhook(
        html_content=html,
        subject=subject,
        metadata={
            "headline": selection.get('headline_title', ''),
            "davis_pattern": selection.get('davis_pattern', ''),
            "source_url": selection.get('headline_url', '')
        }
    )
    
    if success:
        print("=" * 60)
        print("SUCCESS! Newsletter published to Make.com")
        print(f"Draft archived: {draft_path}")
        print("=" * 60)
    else:
        print("=" * 60)
        print("FAILED to publish to Make.com")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
