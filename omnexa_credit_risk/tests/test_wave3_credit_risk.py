# Copyright (c) 2026, Omnexa and contributors

import json

from frappe.tests.utils import FrappeTestCase
import frappe

from omnexa_credit_risk.api import (
	approve_challenger_model_promotion,
	compute_ecl_attribution_bridge,
	persist_credit_risk_calibration_run,
	persist_credit_risk_ecl_movement,
	register_credit_risk_backtest_dataset,
	submit_challenger_model_promotion,
)


class TestCreditRiskWave3(FrappeTestCase):
	def _ensure_user(self, email: str) -> None:
		if frappe.db.exists("User", email):
			return
		doc = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Checker",
				"send_welcome_email": 0,
				"enabled": 1,
			}
		)
		doc.append("roles", {"role": "System Manager"})
		doc.insert(ignore_permissions=True)

	def test_backtest_challenger_calibration_and_ecl_bridge(self):
		dcode = f"DS-{frappe.generate_hash(length=6)}"
		register_credit_risk_backtest_dataset(
			dataset_code=dcode,
			title="Q1 retail",
			segment="RETAIL",
			manifest_json=json.dumps({"rows": 1000}),
			champion_model_version="v1",
			challenger_model_version="v2",
		)
		submit_challenger_model_promotion(dcode)
		self._ensure_user("checker_wave3_risk@example.com")
		frappe.set_user("checker_wave3_risk@example.com")
		approve_challenger_model_promotion(dcode)
		frappe.set_user("Administrator")
		self.assertEqual(
			frappe.db.get_value("Credit Risk Backtest Dataset", dcode, "workflow_status"),
			"CHALLENGER_ACTIVE",
		)

		cal = persist_credit_risk_calibration_run(
			segment="RETAIL",
			horizon_months=36,
			pd_term_json=json.dumps({"1m": "0.01", "12m": "0.04"}),
			lgd_term_json=json.dumps({"base": "0.45"}),
			ead_term_json=json.dumps({"base": "1.0"}),
		)
		self.assertTrue(cal.get("name"))

		opening = [
			{"account_id": "a1", "ecl": "1000", "stage": "STAGE_1"},
			{"account_id": "a2", "ecl": "500", "stage": "STAGE_1"},
		]
		closing = [
			{"account_id": "a1", "ecl": "1200", "stage": "STAGE_2"},
			{"account_id": "a2", "ecl": "500", "stage": "STAGE_1"},
			{"account_id": "a3", "ecl": "300", "stage": "STAGE_1"},
		]
		bridge = compute_ecl_attribution_bridge(json.dumps(opening), json.dumps(closing))
		self.assertIn("attribution", bridge)
		persisted = persist_credit_risk_ecl_movement(
			"2026-Q1",
			"2026-01-01",
			"2026-03-31",
			json.dumps(opening),
			json.dumps(closing),
		)
		self.assertTrue(persisted.get("name"))
