#!/usr/bin/env python3
"""
Generate MP3 audio files for X32 Training Hub lessons using edge-tts.

Usage:
    pip install edge-tts
    python3 scripts/generate_audio.py

Generates: audio/lesson-{id}.mp3 for each lesson (1-8)

Voice: en-US-GuyNeural (Microsoft neural TTS, free via edge-tts)
"""
import asyncio
import os
import re
import json
import subprocess
import sys

VOICE = "en-US-GuyNeural"
OUTPUT_DIR = "audio"
HTML_FILE = "index.html"


def extract_lesson_js(html_path):
    """Pull the const L=[...]; block out of index.html."""
    with open(html_path, encoding="utf-8") as f:
        content = f.read()
    # Find from 'const L=[' to the closing '];'
    start = content.find("const L=[")
    if start == -1:
        raise ValueError("Could not find 'const L=[' in HTML file")
    # Find the closing ]; that ends the lessons array
    # Count bracket depth to find the matching ];
    depth = 0
    pos = start + len("const L=")
    end = -1
    for i in range(pos, len(content)):
        if content[i] == "[":
            depth += 1
        elif content[i] == "]":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end == -1:
        raise ValueError("Could not find closing ]; for const L=")
    return content[start : end + 1]  # includes 'const L=[...];'


def lesson_to_text(lesson):
    """
    Convert a lesson dict to plain readable text — mirrors the JS lessonToText().
    Handles all section types: rules, terms, steps, quote, callout-*, compare,
    trouble, mreqs, meter, mute.
    """
    parts = [lesson["title"] + "."]
    if lesson.get("summary"):
        parts.append(lesson["summary"])

    for s in lesson.get("sec", []):
        if not s or not s.get("t"):
            continue
        sec_type = s["t"]
        if s.get("h"):
            parts.append(s["h"] + ".")
        if s.get("c"):
            parts.append(s["c"])

        if sec_type == "compare" and s.get("a") and s.get("b"):
            a, b = s["a"], s["b"]
            parts.append(f"Comparing {a.get('title','')} and {b.get('title','')}.")
            for item in a.get("items", []):
                parts.append(f"{a.get('title','')}: {item}")
            for item in b.get("items", []):
                parts.append(f"{b.get('title','')}: {item}")

        for it in s.get("items", []):
            if isinstance(it, str):
                parts.append(it)
            elif "r" in it:  # rules
                parts.append(it["r"] + (": " + it["d"] if it.get("d") else "") + ".")
            elif "term" in it:  # terms
                parts.append(it["term"] + (": " + it["def"] if it.get("def") else "") + ".")
            elif "title" in it:  # steps / zone list
                parts.append(it["title"] + (": " + it["desc"] if it.get("desc") else "") + ".")
            elif "p" in it:  # trouble items
                parts.append(it["p"] + (": " + it["c"] if it.get("c") else "") + ".")
            elif "says" in it:  # mreqs
                says = it["says"].strip('"').strip("'")
                do = it.get("do", "")
                parts.append(f"When someone says {says}, {do}.")

    # Strip HTML tags, collapse whitespace
    text = " ".join(parts)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_lessons_via_node(js_text):
    """
    Use Node.js to evaluate the lesson JS and return lesson dicts.
    Falls back to regex extraction if Node is unavailable.
    """
    node_script = f"""
{js_text}
// Output as JSON
process.stdout.write(JSON.stringify(L));
"""
    try:
        result = subprocess.run(
            ["node", "-e", node_script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            print(f"Node error: {result.stderr[:200]}", file=sys.stderr)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"Node unavailable: {e}", file=sys.stderr)
    return None


async def generate_mp3(lesson_id, text, output_path):
    """Generate a single MP3 file using edge-tts."""
    import edge_tts

    communicate = edge_tts.Communicate(text, VOICE)
    await communicate.save(output_path)
    size_kb = os.path.getsize(output_path) // 1024
    print(f"  ✓ lesson-{lesson_id}.mp3 ({size_kb} KB, {len(text)} chars)")


async def main():
    # Check edge-tts is installed
    try:
        import edge_tts
    except ImportError:
        print("ERROR: edge-tts not installed. Run: pip install edge-tts")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"Extracting lesson data from {HTML_FILE} ...")
    lesson_js = extract_lesson_js(HTML_FILE)

    # Try Node.js first (most accurate), fall back is not implemented here
    lessons = extract_lessons_via_node(lesson_js)
    if not lessons:
        print("ERROR: Could not parse lesson data via Node.js")
        sys.exit(1)

    print(f"Found {len(lessons)} lessons. Generating audio with voice '{VOICE}' ...")
    total_chars = 0

    for lesson in lessons:
        lid = lesson["id"]
        text = lesson_to_text(lesson)
        total_chars += len(text)
        output_path = os.path.join(OUTPUT_DIR, f"lesson-{lid}.mp3")
        await generate_mp3(lid, text, output_path)

    print(f"\nDone! {len(lessons)} MP3s generated ({total_chars} total chars)")
    print(f"Files saved to: {OUTPUT_DIR}/")


if __name__ == "__main__":
    asyncio.run(main())
