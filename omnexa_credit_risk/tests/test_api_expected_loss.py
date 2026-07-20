from frappe.tests.utils import FrappeTestCase

from omnexa_credit_risk.api import evaluate_portfolio_expected_loss


class TestExpectedLossApi(FrappeTestCase):
	def test_evaluate_portfolio_expected_loss(self):
		out = evaluate_portfolio_expected_loss(
			exposures=[
				{"segment": "Retail", "pd": "0.02", "lgd": "0.45", "ead": "100000"
	},
				{"segment": "SME", "pd": "0.03", "lgd": "0.40", "ead": "50000"
	},
			],
			scenario={"name": "Downturn", "pd_multiplier": "1.3", "lgd_multiplier": "1.1", "ead_multiplier": "1.0"
	},
		)
		self.assertIn("baseline_expected_loss", out)
		self.assertIn("stressed_expected_loss", out)
		self.assertEqual(len(out["segments"]), 2)

