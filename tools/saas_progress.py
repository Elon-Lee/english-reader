"""Presentation of saved reading position; elapsed study time is not completion."""
from typing import Any

from saas_membership import as_json, timestamp


def reading_progress(row: dict[str, Any], data: Any) -> dict[str, Any]:
    source = as_json(data)
    sentences = source.get("sentences", [])
    sentences = [item for item in sentences if isinstance(item, dict) and str(item.get("text", "")).strip()] if isinstance(sentences, list) else []
    last_id = str(row.get("last_sentence_id") or "")
    position = next((index + 1 for index, item in enumerate(sentences) if str(item.get("id", index)) == last_id), 0) if last_id else 0
    completed = row.get("completed_at")
    # The current sentence is a saved position, not evidence that it was completed.
    percent = 100 if completed else min(99, round(max(0, position - 1) / len(sentences) * 100)) if sentences else 0
    return {"lastSentenceId": last_id, "sentencePosition": position, "percent": percent,
            "readingSeconds": int(row.get("reading_seconds") or 0),
            "completedAt": timestamp(completed), "updatedAt": timestamp(row.get("progress_updated_at"))}
