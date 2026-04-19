from decimal import Decimal

from frappe.tests.utils import FrappeTestCase

from omnexa_credit_risk.engine import (
	AccountExposurePoint,
	BacktestPoint,
	MacroeconomicOverlay,
	ExposurePoint,
	StressScenario,
	aggregate_portfolio_view,
	calculate_account_level_ecl,
	calculate_expected_loss,
	calculate_ifrs9_provisions,
	run_backtesting,
	stress_expected_loss,
)


class TestRiskModel(FrappeTestCase):
	def test_expected_loss_formula(self):
		points = [
			ExposurePoint("Retail", Decimal("0.02"), Decimal("0.45"), Decimal("100000")),
			ExposurePoint("SME", Decimal("0.03"), Decimal("0.40"), Decimal("50000")),
		]
		el = calculate_expected_loss(points)
		self.assertEqual(el, Decimal("1500.0000"))

	def test_stress_expected_loss_greater_than_baseline(self):
		points = [
			ExposurePoint("Retail", Decimal("0.02"), Decimal("0.45"), Decimal("100000")),
		]
		base = calculate_expected_loss(points)
		stress = StressScenario(name="Downturn", pd_multiplier=Decimal("1.5"), lgd_multiplier=Decimal("1.2"))
		stressed, _ = stress_expected_loss(points, stress)
		self.assertGreater(stressed, base)

	def test_ifrs9_stage_and_provisioning(self):
		points = [
			ExposurePoint("Retail", Decimal("0.02"), Decimal("0.45"), Decimal("100000")),
			ExposurePoint("Watchlist", Decimal("0.12"), Decimal("0.50"), Decimal("80000")),
		]
		rows = calculate_ifrs9_provisions(points, defaulted_segments={"Watchlist"})
		self.assertEqual(rows[0].stage, "STAGE_1")
		self.assertEqual(rows[1].stage, "STAGE_3")
		self.assertGreater(rows[1].provision_amount, rows[0].provision_amount)

	def test_account_level_ecl_with_overlay_and_stage(self):
		points = [
			AccountExposurePoint("ACC-1", "Retail", Decimal("0.03"), Decimal("0.45"), Decimal("100000"), dpd=5),
			AccountExposurePoint("ACC-2", "SME", Decimal("0.08"), Decimal("0.50"), Decimal("120000"), dpd=35, sicr_flag=True),
			AccountExposurePoint("ACC-3", "Corp", Decimal("0.20"), Decimal("0.55"), Decimal("80000"), dpd=100, default_flag=True),
		]
		overlay = MacroeconomicOverlay(name="MILD_DOWNTURN", pd_addon=Decimal("0.01"), lgd_addon=Decimal("0.02"))
		rows = calculate_account_level_ecl(points, overlay=overlay)
		self.assertEqual(rows[0].stage, "STAGE_1")
		self.assertEqual(rows[1].stage, "STAGE_2")
		self.assertEqual(rows[2].stage, "STAGE_3")
		pf = aggregate_portfolio_view(rows)
		self.assertEqual(pf["accounts_count"], 3)
		self.assertGreater(pf["total_provision"], Decimal("0"))

	def test_pd_backtesting(self):
		result = run_backtesting(
			[
				BacktestPoint("A1", Decimal("0.02"), 0),
				BacktestPoint("A2", Decimal("0.10"), 1),
				BacktestPoint("A3", Decimal("0.08"), 0),
			]
		)
		self.assertEqual(result.total_accounts, 3)
		self.assertIn(result.accuracy_band, {"STRONG", "ACCEPTABLE", "WEAK"})

