import unittest
from importdoc.modules.confidence import ConfidenceCalculator

class TestConfidence(unittest.TestCase):
    def test_confidence_calculator(self):
        evidence = {
            "ast_definition": 1,
            "ast_usage": 2,
            "syspath_resolvable": 1,
        }
        score, explanation = ConfidenceCalculator.calculate(evidence, 1)
        self.assertGreater(score, 0)
        self.assertIn("ast_definition", explanation)
        self.assertIn("ast_usage", explanation)
        self.assertIn("syspath_resolvable", explanation)

if __name__ == "__main__":
    unittest.main()
