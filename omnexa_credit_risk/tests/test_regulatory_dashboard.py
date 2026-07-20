from frappe.tests.utils import FrappeTestCase

from omnexa_credit_risk.api import get_regulatory_dashboard


class TestCreditRiskRegulatoryDashboard(FrappeTestCase):
	def test_get_regulatory_dashboard(self):
		out = get_regulatory_dashboard()
		self.assertEqual(out["app"], "omnexa_credit_risk")
		self.assertIn("standards", out)
		self.assertIn("governance", out)
		self.assertIn("compliance_score", out)
		self.assertGreaterEqual(out["compliance_score"], 0)
