# Copyright (c) 2026, Omnexa and contributors
# License: MIT. See license.txt

from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from frappe.utils import nowdate

import frappe

from .engine import (
	AccountExposurePoint,
	BacktestPoint,
	ExposurePoint,
	MacroeconomicOverlay,
	StressScenario,
	aggregate_portfolio_view,
	calculate_account_level_ecl,
	calculate_expected_loss,
	calculate_ifrs9_provisions,
	run_backtesting,
	stress_expected_loss,
)
from .standards_profile import get_standards_profile as _get_standards_profile


@frappe.whitelist()
def get_standards_profile() -> dict:
	"""Expose standards profile for governance dashboards and audits."""
	return _get_standards_profile()


@frappe.whitelist()
def evaluate_portfolio_expected_loss(exposures: list[dict], scenario: dict | None = None) -> dict:
	"""
	Evaluate baseline and stressed expected loss.
	`exposures` items: {segment, pd, lgd, ead}
	"""
	points = [
		ExposurePoint(
			segment=str(row.get("segment") or "UNSPECIFIED"),
			pd=Decimal(str(row.get("pd"))),
			lgd=Decimal(str(row.get("lgd"))),
			ead=Decimal(str(row.get("ead"))),
		)
		for row in (exposures or [])
	]
	base_el = calculate_expected_loss(points)
	out = {
		"baseline_expected_loss": str(base_el),
		"segments": [
			{
				"segment": p.segment,
				"pd": str(p.pd),
				"lgd": str(p.lgd),
				"ead": str(p.ead),
				"segment_expected_loss": str(p.pd * p.lgd * p.ead),
			}
			for p in points
		],
	}
	if scenario:
		sc = StressScenario(
			name=str(scenario.get("name") or "STRESS"),
			pd_multiplier=Decimal(str(scenario.get("pd_multiplier", "1.0"))),
			lgd_multiplier=Decimal(str(scenario.get("lgd_multiplier", "1.0"))),
			ead_multiplier=Decimal(str(scenario.get("ead_multiplier", "1.0"))),
		)
		stressed_el, stressed_points = stress_expected_loss(points, sc)
		out["stressed_expected_loss"] = str(stressed_el)
		out["stressed_segments"] = [
			{
				"segment": p.segment,
				"pd": str(p.pd),
				"lgd": str(p.lgd),
				"ead": str(p.ead),
				"segment_expected_loss": str(p.pd * p.lgd * p.ead),
			}
			for p in stressed_points
		]
	provisions = calculate_ifrs9_provisions(
		points,
		defaulted_segments={
			str(row.get("segment"))
			for row in (exposures or [])
			if bool(row.get("defaulted"))
		},
	)
	out["ifrs9_provisions"] = [
		{
			"segment": p.segment,
			"stage": p.stage,
			"provision_rate": str(p.provision_rate),
			"provision_amount": str(p.provision_amount),
		}
		for p in provisions
	]
	out["total_provision_amount"] = str(sum((p.provision_amount for p in provisions), Decimal("0")))
	return out


def _build_ecl_bridge(opening: list[dict], closing: list[dict]) -> dict:
	"""Opening/closing account snapshots: {account_id, ecl, stage?}."""
	by_o = {str(r.get("account_id")): r for r in (opening or [])}
	by_c = {str(r.get("account_id")): r for r in (closing or [])}
	total_o = sum((Decimal(str(r.get("ecl", 0))) for r in (opening or [])), Decimal("0"))
	total_c = sum((Decimal(str(r.get("ecl", 0))) for r in (closing or [])), Decimal("0"))
	new_orig = Decimal("0")
	closed = Decimal("0")
	stage_xfer = Decimal("0")
	other = Decimal("0")
	all_ids = set(by_o) | set(by_c)
	for aid in all_ids:
		o = by_o.get(aid)
		c = by_c.get(aid)
		if o and c:
			de = Decimal(str(c.get("ecl", 0))) - Decimal(str(o.get("ecl", 0)))
			if str(o.get("stage")) != str(c.get("stage")):
				stage_xfer += de
			else:
				other += de
		elif c and not o:
			new_orig += Decimal(str(c.get("ecl", 0)))
		elif o and not c:
			closed -= Decimal(str(o.get("ecl", 0)))
	return {
		"opening_total_ecl": str(total_o),
		"closing_total_ecl": str(total_c),
		"net_movement": str(total_c - total_o),
		"attribution": {
			"new_and_defaults": str(new_orig + closed),
			"stage_transfers": str(stage_xfer),
			"parameter_rollover": str(other),
		},
	}


@frappe.whitelist()
def compute_ecl_attribution_bridge(opening_accounts: str, closing_accounts: str) -> dict:
	o = json.loads(opening_accounts) if isinstance(opening_accounts, str) else opening_accounts
	c = json.loads(closing_accounts) if isinstance(closing_accounts, str) else closing_accounts
	return _build_ecl_bridge(o, c)


@frappe.whitelist()
def persist_credit_risk_ecl_movement(
	period_label: str,
	period_start: str,
	period_end: str,
	opening_accounts: str,
	closing_accounts: str,
) -> dict:
	bridge = _build_ecl_bridge(json.loads(opening_accounts), json.loads(closing_accounts))
	doc = frappe.get_doc(
		{
			"doctype": "Credit Risk ECL Movement",
			"period_label": period_label,
			"period_start": period_start,
			"period_end": period_end,
			"opening_total_ecl": bridge["opening_total_ecl"],
			"closing_total_ecl": bridge["closing_total_ecl"],
			"net_movement": bridge["net_movement"],
			"bridge_json": json.dumps(bridge, sort_keys=True),
		}
	)
	doc.insert(ignore_permissions=True)
	return {"name": doc.name, "bridge": bridge}


@frappe.whitelist()
def register_credit_risk_backtest_dataset(
	dataset_code: str,
	title: str,
	segment: str,
	manifest_json: str,
	champion_model_version: str,
	challenger_model_version: str = "",
) -> dict:
	if frappe.db.exists("Credit Risk Backtest Dataset", dataset_code):
		doc = frappe.get_doc("Credit Risk Backtest Dataset", dataset_code)
	else:
		doc = frappe.new_doc("Credit Risk Backtest Dataset")
		doc.dataset_code = dataset_code
	doc.title = title
	doc.segment = segment
	doc.manifest_json = manifest_json
	doc.champion_model_version = champion_model_version
	doc.challenger_model_version = challenger_model_version
	doc.save(ignore_permissions=True)
	return {"dataset_code": dataset_code, "name": doc.name}


@frappe.whitelist()
def submit_challenger_model_promotion(dataset_code: str) -> dict:
	from frappe.utils import now_datetime

	doc = frappe.get_doc("Credit Risk Backtest Dataset", dataset_code)
	doc.workflow_status = "CHALLENGER_PENDING_APPROVAL"
	doc.promotion_submitted_by = frappe.session.user
	doc.promotion_submitted_on = now_datetime()
	doc.promotion_approved_by = None
	doc.promotion_approved_on = None
	doc.save(ignore_permissions=True)
	return {"dataset_code": dataset_code, "workflow_status": doc.workflow_status}


@frappe.whitelist()
def approve_challenger_model_promotion(dataset_code: str) -> dict:
	from frappe.utils import now_datetime

	doc = frappe.get_doc("Credit Risk Backtest Dataset", dataset_code)
	if doc.workflow_status != "CHALLENGER_PENDING_APPROVAL":
		frappe.throw(frappe._("Challenger promotion is not pending"))
	if doc.promotion_submitted_by == frappe.session.user:
		frappe.throw(frappe._("Checker must differ from maker"))
	doc.workflow_status = "CHALLENGER_ACTIVE"
	doc.promotion_approved_by = frappe.session.user
	doc.promotion_approved_on = now_datetime()
	doc.save(ignore_permissions=True)
	return {"dataset_code": dataset_code, "workflow_status": doc.workflow_status}


@frappe.whitelist()
def persist_credit_risk_calibration_run(
	segment: str,
	horizon_months: int,
	pd_term_json: str,
	lgd_term_json: str,
	ead_term_json: str,
	calibration_method: str = "TERM_BOOTSTRAP",
	valuation_date: str | None = None,
) -> dict:
	doc = frappe.get_doc(
		{
			"doctype": "Credit Risk Calibration Run",
			"segment": segment,
			"valuation_date": valuation_date or nowdate(),
			"horizon_months": int(horizon_months),
			"pd_term_json": pd_term_json,
			"lgd_term_json": lgd_term_json,
			"ead_term_json": ead_term_json,
			"calibration_method": calibration_method,
			"status": "COMPLETED",
		}
	)
	doc.insert(ignore_permissions=True)
	return {"name": doc.name, "segment": segment}


@frappe.whitelist()
def evaluate_account_level_risk(
	exposures: list[dict],
	overlay: dict | None = None,
	stress_scenarios: list[dict] | None = None,
) -> dict:
	"""
	Account and portfolio level ECL with IFRS9 staging, macro overlays and stress scenarios.
	`exposures` items:
	{
		account_id, segment, pd, lgd, ead,
		dpd, sicr_flag, default_flag, country_code, product_code
	}
	"""
	points = [
		AccountExposurePoint(
			account_id=str(row.get("account_id") or ""),
			segment=str(row.get("segment") or "UNSPECIFIED"),
			pd=Decimal(str(row.get("pd"))),
			lgd=Decimal(str(row.get("lgd"))),
			ead=Decimal(str(row.get("ead"))),
			dpd=int(row.get("dpd") or 0),
			sicr_flag=bool(row.get("sicr_flag")),
			default_flag=bool(row.get("default_flag")),
			country_code=str(row.get("country_code") or "INTL"),
			product_code=str(row.get("product_code") or "GENERIC"),
		)
		for row in (exposures or [])
	]
	overlay_obj = None
	if overlay:
		overlay_obj = MacroeconomicOverlay(
			name=str(overlay.get("name") or "BASE_OVERLAY"),
			pd_addon=Decimal(str(overlay.get("pd_addon", "0"))),
			lgd_addon=Decimal(str(overlay.get("lgd_addon", "0"))),
			ead_addon_multiplier=Decimal(str(overlay.get("ead_addon_multiplier", "0"))),
		)
	results = calculate_account_level_ecl(points, overlay=overlay_obj)
	portfolio = aggregate_portfolio_view(results)
	out = {
		"portfolio_view": {
			"accounts_count": portfolio["accounts_count"],
			"total_ecl": str(portfolio["total_ecl"]),
			"total_provision": str(portfolio["total_provision"]),
			"stage_breakdown": {
				k: str(v) for k, v in portfolio["stage_breakdown"].items()
			},
		},
		"account_view": [
			{
				"account_id": r.account_id,
				"segment": r.segment,
				"stage": r.stage,
				"pd": str(r.pd),
				"lgd": str(r.lgd),
				"ead": str(r.ead),
				"ecl": str(r.ecl),
				"provision_rate": str(r.provision_rate),
				"provision_amount": str(r.provision_amount),
				"country_code": r.country_code,
				"product_code": r.product_code,
			}
			for r in results
		],
	}
	if stress_scenarios:
		out["stress_testing"] = _run_account_stress_testing(points=points, stress_scenarios=stress_scenarios)
	return out


@frappe.whitelist()
def run_pd_model_backtesting(points: list[dict]) -> dict:
	"""
	Historical backtesting for PD calibration.
	`points` items: {account_id, predicted_pd, observed_default}
	"""
	val = run_backtesting(
		[
			BacktestPoint(
				account_id=str(p.get("account_id") or ""),
				predicted_pd=Decimal(str(p.get("predicted_pd"))),
				observed_default=int(p.get("observed_default") or 0),
			)
			for p in (points or [])
		]
	)
	return {
		"total_accounts": val.total_accounts,
		"observed_default_rate": str(val.observed_default_rate),
		"average_predicted_pd": str(val.average_predicted_pd),
		"brier_score": str(val.brier_score),
		"accuracy_band": val.accuracy_band,
		"threshold_breaches": _threshold_breaches(val),
	}


@frappe.whitelist()
def persist_portfolio_stress_run(run_name: str, valuation_date: str | None, exposures: list[dict], stress_scenarios: list[dict]) -> dict:
	base = evaluate_account_level_risk(exposures=exposures)
	stress = evaluate_account_level_risk(exposures=exposures, stress_scenarios=stress_scenarios)
	payload = {"exposures": exposures, "stress_scenarios": stress_scenarios}
	input_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
	doc = frappe.get_doc(
		{
			"doctype": "Credit Risk Portfolio Stress Run",
			"run_name": run_name,
			"valuation_date": valuation_date or nowdate(),
			"scenario_payload": json.dumps(stress_scenarios, sort_keys=True),
			"input_hash": input_hash,
			"base_total_ecl": base["portfolio_view"]["total_ecl"],
			"stressed_total_ecl": stress.get("stress_testing", [{}])[-1].get("total_ecl"),
			"base_total_provision": base["portfolio_view"]["total_provision"],
			"stressed_total_provision": stress.get("stress_testing", [{}])[-1].get("total_provision"),
			"result_json": json.dumps(stress, sort_keys=True, default=str),
		}
	)
	doc.insert(ignore_permissions=True)
	return {"name": doc.name, "run_name": run_name}


@frappe.whitelist()
def persist_model_validation_run(model_name: str, dataset_ref: str, points: list[dict], validation_date: str | None = None) -> dict:
	result = run_pd_model_backtesting(points=points)
	doc = frappe.get_doc(
		{
			"doctype": "Credit Risk Model Validation Run",
			"model_name": model_name,
			"validation_date": validation_date or nowdate(),
			"dataset_ref": dataset_ref,
			"total_accounts": result["total_accounts"],
			"observed_default_rate": result["observed_default_rate"],
			"average_predicted_pd": result["average_predicted_pd"],
			"brier_score": result["brier_score"],
			"accuracy_band": result["accuracy_band"],
			"threshold_breaches_json": json.dumps(result["threshold_breaches"], sort_keys=True),
		}
	)
	doc.insert(ignore_permissions=True)
	return {"name": doc.name, "model_name": model_name}


@frappe.whitelist()
def integrate_credit_decisions(decisions: list[dict], snapshot_date: str | None = None, macro_overlay: dict | None = None) -> dict:
	"""
	Integrate credit decisions and materialize account-level risk snapshots.
	`decisions` items typically mapped from Credit Decision Case:
	{case_id, account_id, country_code, product_code, customer_segment, score, request_amount, current_exposure}
	"""
	exposures = []
	for d in (decisions or []):
		score = Decimal(str(d.get("score", 0)))
		pd = _score_to_pd(score)
		lgd = Decimal("0.45")
		ead = Decimal(str(d.get("current_exposure") or d.get("request_amount") or "0"))
		exposures.append(
			{
				"account_id": str(d.get("account_id") or d.get("case_id") or ""),
				"segment": str(d.get("customer_segment") or "UNSPECIFIED"),
				"pd": str(pd),
				"lgd": str(lgd),
				"ead": str(ead),
				"country_code": str(d.get("country_code") or "INTL"),
				"product_code": str(d.get("product_code") or "GENERIC"),
				"default_flag": False,
			}
		)
	result = evaluate_account_level_risk(exposures=exposures, overlay=macro_overlay)
	persisted = 0
	for row in result.get("account_view", []):
		doc = frappe.get_doc(
			{
				"doctype": "Credit Risk Account Snapshot",
				"account_id": row["account_id"],
				"segment": row["segment"],
				"country_code": row["country_code"],
				"product_code": row["product_code"],
				"snapshot_date": snapshot_date or nowdate(),
				"ifrs9_stage": row["stage"],
				"pd": row["pd"],
				"lgd": row["lgd"],
				"ead": row["ead"],
				"ecl": row["ecl"],
				"provision_rate": row["provision_rate"],
				"provision_amount": row["provision_amount"],
			}
		)
		doc.insert(ignore_permissions=True)
		persisted += 1
	return {
		"persisted_snapshots": persisted,
		"portfolio_view": result["portfolio_view"],
	}


@frappe.whitelist()
def submit_policy_version(policy_name: str, version: str, payload: str, effective_from: str | None = None) -> dict:
	import json
	from .governance import submit_policy_version as _submit
	obj = json.loads(payload) if isinstance(payload, str) else payload
	if not isinstance(obj, dict):
		frappe.throw(frappe._("payload must be a JSON object"))
	return _submit("omnexa_credit_risk", policy_name=policy_name, version=version, payload=obj, effective_from=effective_from)


@frappe.whitelist()
def approve_policy_version(policy_name: str, version: str) -> dict:
	from .governance import approve_policy_version as _approve
	return _approve("omnexa_credit_risk", policy_name=policy_name, version=version)


@frappe.whitelist()
def create_audit_snapshot(process_name: str, inputs: str, outputs: str, policy_ref: str | None = None) -> dict:
	import json
	from .governance import create_audit_snapshot as _snap
	in_obj = json.loads(inputs) if isinstance(inputs, str) else inputs
	out_obj = json.loads(outputs) if isinstance(outputs, str) else outputs
	if not isinstance(in_obj, dict) or not isinstance(out_obj, dict):
		frappe.throw(frappe._("inputs/outputs must be JSON objects"))
	return _snap("omnexa_credit_risk", process_name=process_name, inputs=in_obj, outputs=out_obj, policy_ref=policy_ref)


@frappe.whitelist()
def get_governance_overview() -> dict:
	from .governance import governance_overview as _overview
	return _overview("omnexa_credit_risk")


@frappe.whitelist()
def reject_policy_version(policy_name: str, version: str, reason: str = "") -> dict:
	from .governance import reject_policy_version as _reject
	return _reject("omnexa_credit_risk", policy_name=policy_name, version=version, reason=reason)


@frappe.whitelist()
def list_policy_versions(policy_name: str | None = None) -> list[dict]:
	from .governance import list_policy_versions as _list
	return _list("omnexa_credit_risk", policy_name=policy_name)


@frappe.whitelist()
def list_audit_snapshots(process_name: str | None = None, limit: int = 100) -> list[dict]:
	from .governance import list_audit_snapshots as _list
	return _list("omnexa_credit_risk", process_name=process_name, limit=int(limit))


@frappe.whitelist()
def get_regulatory_dashboard() -> dict:
	"""Unified compliance dashboard payload for this app."""
	from .governance import governance_overview
	from .standards_profile import get_standards_profile
	std = get_standards_profile()
	gov = governance_overview("omnexa_credit_risk")
	return {
		"app": "omnexa_credit_risk",
		"standards": std.get("standards", []),
		"activity_controls": std.get("activity_controls", []),
		"governance": gov,
		"compliance_score": _compute_compliance_score(std=std, gov=gov),
	}


@frappe.whitelist()
def get_regulatory_reporting_pack(as_of_date: str | None = None) -> dict:
	"""
	Regulatory reporting structure for Basel III / IFRS9:
	- portfolio summary
	- IFRS9 stage mix
	- latest stress runs
	- latest model validation runs
	"""
	as_of_date = as_of_date or nowdate()
	stage_rows = frappe.db.sql(
		"""
		select ifrs9_stage, count(*) as accounts, sum(ifnull(provision_amount, 0)) as total_provision
		from `tabCredit Risk Account Snapshot`
		where snapshot_date = %(as_of_date)s
		group by ifrs9_stage
		order by ifrs9_stage
		""",
		{"as_of_date": as_of_date},
		as_dict=True,
	)
	stress_rows = frappe.get_all(
		"Credit Risk Portfolio Stress Run",
		fields=["name", "run_name", "valuation_date", "base_total_ecl", "stressed_total_ecl", "base_total_provision", "stressed_total_provision"],
		order_by="creation desc",
		limit_page_length=10,
	)
	validation_rows = frappe.get_all(
		"Credit Risk Model Validation Run",
		fields=["name", "model_name", "validation_date", "brier_score", "accuracy_band"],
		order_by="creation desc",
		limit_page_length=10,
	)
	return {
		"as_of_date": as_of_date,
		"ifrs9_stage_mix": stage_rows,
		"stress_runs": stress_rows,
		"model_validations": validation_rows,
	}


def _compute_compliance_score(std: dict, gov: dict) -> int:
	"""Simple normalized readiness score (0..100) for executive monitoring."""
	base = min(50, 5 * len(std.get("standards", [])))
	controls = min(30, 3 * len(std.get("activity_controls", [])))
	approved = int(gov.get("policies_approved", 0) or 0)
	pending = int(gov.get("policies_pending", 0) or 0)
	governance = min(20, approved * 2)
	if pending > 0:
		governance = max(0, governance - min(10, pending))
	return int(base + controls + governance)


def _run_account_stress_testing(points: list[AccountExposurePoint], stress_scenarios: list[dict]) -> list[dict]:
	out = []
	for sc in stress_scenarios:
		overlay = MacroeconomicOverlay(
			name=str(sc.get("name") or "STRESS"),
			pd_addon=Decimal(str(sc.get("pd_addon", "0"))),
			lgd_addon=Decimal(str(sc.get("lgd_addon", "0"))),
			ead_addon_multiplier=Decimal(str(sc.get("ead_addon_multiplier", "0"))),
		)
		results = calculate_account_level_ecl(points, overlay=overlay)
		portfolio = aggregate_portfolio_view(results)
		out.append(
			{
				"scenario": overlay.name,
				"total_ecl": str(portfolio["total_ecl"]),
				"total_provision": str(portfolio["total_provision"]),
				"stage_breakdown": {k: str(v) for k, v in portfolio["stage_breakdown"].items()},
			}
		)
	return out


def _threshold_breaches(val) -> list[dict]:
	breaches = []
	if val.brier_score > Decimal("0.20"):
		breaches.append({"metric": "brier_score", "severity": "HIGH", "message": "Brier score above model threshold"})
	pd_gap = abs(val.average_predicted_pd - val.observed_default_rate)
	if pd_gap > Decimal("0.05"):
		breaches.append({"metric": "pd_calibration_gap", "severity": "MEDIUM", "message": "Predicted PD deviates from observed default rate"})
	return breaches


def _score_to_pd(score: Decimal) -> Decimal:
	# Simple monotonic mapping ready to be replaced by calibrated PD curves.
	if score >= Decimal("800"):
		return Decimal("0.01")
	if score >= Decimal("700"):
		return Decimal("0.03")
	if score >= Decimal("620"):
		return Decimal("0.07")
	return Decimal("0.15")

@frappe.whitelist()
def preview_gl_posting(
	scenario: str | None = None,
	rou_asset: str = "0",
	lease_liability: str = "0",
	principal: str = "0",
	settlement_cash: str = "0",
) -> dict:
	"""SAP parity — GL preview (finance_engine bridge, no JE)."""
	from omnexa_finance_engine.fs_parity_bridge import preview_gl_for_vertical
	return preview_gl_for_vertical(
		"credit_risk",
		scenario=scenario,
		rou_asset=rou_asset,
		lease_liability=lease_liability,
		principal=principal,
		settlement_cash=settlement_cash,
	)

