#!/usr/bin/env python3
import unittest

from library_db import normalize_confirmation_title

class DeleteBookConfirmationTests(unittest.TestCase):
    def test_all_unicode_whitespace_is_ignored(self):
        title="How to THINK in English | No More Translating in Your Head!"
        entered="How to\tTHINK\nin\rEnglish\u3000| No More Translating in Your Head!"
        self.assertEqual(normalize_confirmation_title(entered),normalize_confirmation_title(title))

    def test_non_whitespace_characters_must_still_match(self):
        self.assertNotEqual(normalize_confirmation_title("简 爱"),normalize_confirmation_title("简·爱"))

if __name__=="__main__":unittest.main()
