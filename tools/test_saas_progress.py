import unittest
from datetime import datetime, timezone
from saas_progress import reading_progress


class ReadingPositionTests(unittest.TestCase):
    def test_elapsed_time_does_not_claim_completion(self):
        data = {"sentences": [{"id": "a", "text": "First"}, {"id": "b", "text": "Second"}]}
        result = reading_progress({"reading_seconds": 99999, "last_sentence_id": "b"}, data)
        self.assertEqual(result["percent"], 50)
        self.assertEqual(result["sentencePosition"], 2)

    def test_missing_position_and_empty_content(self):
        self.assertEqual(reading_progress({"last_sentence_id": "missing"}, {"sentences": []})["percent"], 0)
        self.assertEqual(reading_progress({}, {})["sentencePosition"], 0)

    def test_last_position_does_not_round_to_completion(self):
        data = {"sentences": [{"id": str(i), "text": "Sentence"} for i in range(1000)]}
        self.assertEqual(reading_progress({"last_sentence_id": "999"}, data)["percent"], 99)

    def test_completion_and_latest_activity_are_preserved(self):
        now = datetime(2026, 10, 19, tzinfo=timezone.utc)
        result = reading_progress({"completed_at": now, "progress_updated_at": now}, {})
        self.assertEqual(result["percent"], 100)
        self.assertIsNotNone(result["updatedAt"])


if __name__ == '__main__':
    unittest.main()
