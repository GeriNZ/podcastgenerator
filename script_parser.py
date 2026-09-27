"""Script validation only; no models or local project dependencies."""
import re
MAX_INPUT_BYTES = 1_000_000
MAX_WORDS = 60
MAX_CHUNK_WORDS = 35

def parse_script(text):
    """Accept A:/B: dialogue and the original timestamped Speaker 1/0 format."""
    if len(text.encode('utf-8')) > MAX_INPUT_BYTES:
        raise ValueError('Please use a script smaller than 1 MB.')
    turns = []
    speaker = None
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        match = re.fullmatch(r'(?:(?:\d+:)?\d+:\d+\s+)?(Speaker\s*[01]|A|B)\s*(?::\s*(.*))?', line, re.I)
        if match:
            label, content = match.groups()
            speaker = 'A' if label.upper() == 'A' or re.fullmatch(r'Speaker\s*1', label, re.I) else 'B'
            if content:
                turns.append({'speaker': speaker, 'text': content.strip()})
        elif speaker:
            if turns and turns[-1]['speaker'] == speaker:
                turns[-1]['text'] += ' ' + line
            else:
                turns.append({'speaker': speaker, 'text': line})
        else:
            raise ValueError(f'Line {number}: start dialogue with A: or B:.')
    if not turns:
        raise ValueError('Add some dialogue after A: or B:.')
    total_words = sum(len(t['text'].split()) for t in turns)
    remaining = MAX_WORDS
    chunks = []
    for turn in turns:
        words = turn['text'].split()[:remaining]
        remaining -= len(words)
        # Prefer sentence boundaries, but bound long sentences as well.
        for sentence in re.split(r'(?<=[.!?])\s+', ' '.join(words)):
            parts = sentence.split()
            for start in range(0, len(parts), MAX_CHUNK_WORDS):
                chunks.append({'speaker': turn['speaker'], 'text': ' '.join(parts[start:start + MAX_CHUNK_WORDS])})
        if remaining == 0:
            break
    return chunks, total_words > MAX_WORDS
