from frappe.tests.utils import FrappeTestCase

from omnexa_credit_risk.api import evaluate_account_level_risk, run_pd_model_backtesting


class TestAdvancedRiskApi(FrappeTestCase):
	def test_account_level_risk_with_overlay_and_stress(self):
		out = evaluate_account_level_risk(
			exposures=[
				{
					"account_id": "ACC-1001",
					"segment": "Retail",
					"pd": "0.03",
					"lgd": "0.45",
					"ead": "80000",
					"dpd": 10
	},
				{
					"account_id": "ACC-1002",
					"segment": "SME",
					"pd": "0.12",
					"lgd": "0.50",
					"ead": "120000",
					"dpd": 45,
					"sicr_flag": 1
	},
			],
			overlay={"name": "BASELINE_OVERLAY", "pd_addon": "0.01", "lgd_addon": "0.02"
	},
			stress_scenarios=[
				{"name": "Severe Recession", "pd_addon": "0.03", "lgd_addon": "0.05", "ead_addon_multiplier": "0.10"
	}
			],
		)
		self.assertIn("portfolio_view", out)
		self.assertIn("account_view", out)
		self.assertIn("stress_testing", out)
		self.assertEqual(len(out["account_view"]), 2)

	def test_run_pd_model_backtesting(self):
		out = run_pd_model_backtesting(
			points=[
				{"account_id": "A1", "predicted_pd": "0.02", "observed_default": 0
	},
				{"account_id": "A2", "predicted_pd": "0.08", "observed_default": 0
	},
				{"account_id": "A3", "predicted_pd": "0.15", "observed_default": 1
	},
			]
		)
		self.assertEqual(out["total_accounts"], 3)
		self.assertIn("brier_score", out)
		self.assertIn("threshold_breaches", out)

