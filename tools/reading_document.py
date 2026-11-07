"""Original document blocks for new imports; never reconstruct or write old books."""
import re
from text_segmentation import WORD_RE, split_sentences


def build_reading_document(blocks, source_format):
    sentences = []
    output = []
    for original in blocks:
        block = {key: original[key] for key in ("type", "text", "section", "page", "pageLabel") if key in original}
        text = str(block.get("text", "")).strip()
        if not text:
            continue
        block.update(id=f"b-{len(output)+1}", text=text, words=[])
        tokens = list(WORD_RE.finditer(text))
        offset = 0
        for part in split_sentences(text, max_words=60):
            value = re.sub(r"\s+", " ", part).strip()
            words = [{"text": word} for word in WORD_RE.findall(value)]
            sentence_id = f"s-{len(sentences)+1}"
            sentences.append({"id": sentence_id, "text": value, "translation": "", "words": words,
                              **{key: block[key] for key in ("page", "section") if key in block}})
            for index, token in enumerate(tokens[offset:offset+len(words)]):
                # JSON offsets use Unicode code points; the browser converts via Array.from.
                block["words"].append({"start": token.start(), "end": token.end(),
                                       "sentenceId": sentence_id, "wordIndex": index})
            offset += len(words)
        output.append(block)
    return sentences, {"version": 1, "format": source_format,
                       "pagination": "original" if source_format == "pdf" else "reflow",
                       "blocks": output}


def reader_document(data, sentences, trial=False):
    """Expose structure only after book authorization, trimming partial trial blocks."""
    document = data.get("readingDocument")
    if not isinstance(document, dict) or document.get("version") != 1:
        return None
    allowed = {str(sentence["id"]) for sentence in sentences}
    blocks = []
    for original in document.get("blocks", []):
        if not isinstance(original, dict):
            continue
        block = {key: original[key] for key in ("id", "type", "text", "section", "page", "pageLabel", "words") if key in original}
        if trial:
            words = block.get("words", [])
            if not words or not any(str(word.get("sentenceId")) in allowed for word in words):
                continue
            cut = next((word["start"] for word in words if str(word.get("sentenceId")) not in allowed), len(block.get("text", "")))
            block["text"] = block.get("text", "")[:cut].rstrip()
            block["words"] = [word for word in words if str(word.get("sentenceId")) in allowed and word["end"] <= cut]
        blocks.append(block)
    return {"version": 1, "format": document.get("format"),
            "pagination": "reflow" if trial else document.get("pagination", "reflow"), "blocks": blocks,
            **({'source':document['source']} if not trial and document.get('source') else {})}
