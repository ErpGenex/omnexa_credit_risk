# Copyright (c) 2026, Omnexa and contributors
# License: MIT. See license.txt

from __future__ import annotations

import json

import frappe

APP = "omnexa_credit_risk"
WORKSPACE = "Credit Risk Governance"
POLICY_DTYPE = "Credit Risk Policy Version"
SNAP_DTYPE = "Credit Risk Audit Snapshot"
CHART_POL = "Credit Risk Governance - Policies by Status"
CHART_SNP = "Credit Risk Governance - Snapshots (Last Month)"
MODULE = "Omnexa Credit Risk"
ICON = "retail"


def after_migrate():
	ensure_workspace_assets()


def ensure_workspace_assets():
	if not frappe.db.exists("DocType", POLICY_DTYPE):
		return
	_ensure_chart(CHART_POL, chart_type="Group By", document_type=POLICY_DTYPE, group_by_based_on="status", chart_render_type="Donut", timeseries=0)
	_ensure_chart(CHART_SNP, chart_type="Count", document_type=SNAP_DTYPE, based_on="created_at", chart_render_type="Line", timeseries=1)
	_ensure_workspace()


def _ensure_chart(name: str, chart_type: str, document_type: str, chart_render_type: str, timeseries: int, based_on: str | None = None, group_by_based_on: str | None = None):
	if frappe.db.exists("Dashboard Chart", name):
		return
	doc = frappe.get_doc(
		{
			"doctype": "Dashboard Chart",
			"chart_name": name,
			"is_standard": "No",
			"module": MODULE,
			"is_public": 1,
			"chart_type": chart_type,
			"document_type": document_type,
			"group_by_type": "Count",
			"group_by_based_on": group_by_based_on,
			"based_on": based_on,
			"timeseries": timeseries,
			"timespan": "Last Month",
			"time_interval": "Daily",
			"filters_json": "[]",
			"type": chart_render_type,
		}
	)
	doc.insert(ignore_permissions=True)


def _prune_invalid_workspace_references(ws):
	"""Drop child rows and content blocks that point to deleted Number Cards / Charts / DocTypes.

	Migrate may remove DocTypes (e.g. SME stack) while Workspace rows still reference their KPIs;
	without pruning, ``save`` raises LinkValidationError.
	"""
	for row in list(ws.get("number_cards") or []):
		name = getattr(row, "number_card_name", None) or (row or {}).get("number_card_name")
		if name and not frappe.db.exists("Number Card", name):
			ws.remove(row)

	for row in list(ws.get("charts") or []):
		ch = getattr(row, "chart_name", None) or (row or {}).get("chart_name")
		if ch and not frappe.db.exists("Dashboard Chart", ch):
			ws.remove(row)

	for row in list(ws.get("links") or []):
		if getattr(row, "link_type", None) == "DocType" or (row or {}).get("link_type") == "DocType":
			lt = getattr(row, "link_to", None) or (row or {}).get("link_to")
			if lt and not frappe.db.exists("DocType", lt):
				ws.remove(row)

	try:
		blocks = json.loads(ws.content or "[]")
	except Exception:
		blocks = []
	if isinstance(blocks, list):
		filtered = []
		for b in blocks:
			if (b or {}).get("type") == "chart":
				cn = (((b or {}).get("data") or {}).get("chart_name") or "").strip()
				if cn and not frappe.db.exists("Dashboard Chart", cn):
					continue
			filtered.append(b)
		ws.content = json.dumps(filtered)


def _ensure_workspace():
	ws = None
	if frappe.db.exists("Workspace", WORKSPACE):
		try:
			ws = frappe.get_doc("Workspace", WORKSPACE)
		except Exception:
			ws = None
	if not ws:
		ws = frappe.new_doc("Workspace")
		ws.update({"label": WORKSPACE, "title": WORKSPACE, "name": WORKSPACE, "module": MODULE, "public": 1, "icon": ICON})
		ws.insert(ignore_permissions=True)

	ws.icon = ICON
	ws.module = MODULE
	ws.public = 1
	ws.content = json.dumps([
		{"id": "omnexa_credit_risk-h", "type": "header", "data": {"text": "<span class=\"h4\"><b>Credit Risk Governance</b></span>", "col": 12}},
		{"id": "omnexa_credit_risk-c1", "type": "card", "data": {"card_name": "Governance", "col": 4}},
		{"id": "omnexa_credit_risk-ch1", "type": "chart", "data": {"chart_name": CHART_POL, "col": 4}},
		{"id": "omnexa_credit_risk-ch2", "type": "chart", "data": {"chart_name": CHART_SNP, "col": 4}},
	])

	if not ws.get("links"):
		ws.set("links", [])
	if not any((l.get("type") == "Card Break" and l.get("label") == "Governance") for l in ws.links):
		ws.append("links", {"type": "Card Break", "label": "Governance", "hidden": 0})
	for lb, lt in (("Policy Versions", POLICY_DTYPE), ("Audit Snapshots", SNAP_DTYPE)):
		if not any((l.get("type") == "Link" and l.get("link_to") == lt) for l in ws.links):
			ws.append("links", {"type": "Link", "label": lb, "link_type": "DocType", "link_to": lt, "hidden": 0})

	if not ws.get("charts"):
		ws.set("charts", [])
	if not any(c.get("chart_name") == CHART_POL for c in ws.charts):
		ws.append("charts", {"chart_name": CHART_POL, "label": "Policies by Status"})
	if not any(c.get("chart_name") == CHART_SNP for c in ws.charts):
		ws.append("charts", {"chart_name": CHART_SNP, "label": "Snapshots (Last Month)"})

	_prune_invalid_workspace_references(ws)
	ws.save(ignore_permissions=True)
