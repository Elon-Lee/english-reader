#!/usr/bin/env python3
import unittest

from grammar_analysis import GrammarAnalyzer

class GrammarAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.analyzer=GrammarAnalyzer()

    def test_conditional_clause(self):
        result=self.analyzer.analyze("If you work hard, you will succeed.")
        self.assertEqual(result["sentenceType"],"主从复合句")
        self.assertEqual(result["subject"],"you")
        self.assertEqual(result["predicate"],"will succeed")
        self.assertEqual(result["clauses"][0]["type"],"条件状语从句")

    def test_relative_clause_and_copula(self):
        result=self.analyzer.analyze("The book that I bought yesterday is very interesting.")
        self.assertEqual(result["pattern"],"主语 + 系动词 + 表语")
        self.assertIn("定语从句",result["grammarPoints"])

    def test_present_perfect_progressive(self):
        result=self.analyzer.analyze("She has been studying English for three years.")
        self.assertIn("现在完成进行时",result["grammarPoints"])

    def test_inverted_copular_complement(self):
        result=self.analyzer.analyze("A good son, you are!")
        self.assertEqual(result["subject"],"you")
        self.assertEqual(result["predicate"],"are")
        self.assertEqual(result["object"],"A good son")
        self.assertEqual(result["pattern"],"主语 + 系动词 + 表语")

    def test_adverbial_does_not_pollute_predicate_core(self):
        result=self.analyzer.analyze("Joseph saw him two days ago.")
        self.assertEqual(result["predicate"],"saw")

if __name__=="__main__":unittest.main()
