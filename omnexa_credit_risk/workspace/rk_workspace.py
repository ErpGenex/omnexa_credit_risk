# Copyright (c) 2026, Omnexa and contributors
# License: MIT

"""Full Credit Risk workspace — SAP SD / Van Sales parity catalog."""

from __future__ import annotations

import json

import frappe

from omnexa_core.omnexa_core.vertical_workspace_sync import (
	build_link_rows_for_app,
	drop_missing_workspace_dashboard_links,
)

WorkspaceLink = tuple[str, str, str]

WORKSPACE_NAME = "Credit Risk"

_SHORTCUT_COLORS = ("Blue", "Green", "Orange", "Red", "Cyan", "Purple", "Teal", "Pink", "Yellow")

WORKSPACE_SECTIONS: list[tuple[str, list[WorkspaceLink]]] = [('📊 Dashboards', [('Page', 'rk-executive-dashboard', 'Executive Dashboard'), ('Page', 'rk-servicing-portal', 'Servicing Portal')]), ('📉 IFRS9 & ECL', [('DocType', 'Credit Risk Account Snapshot', 'Account Snapshot'), ('DocType', 'Credit Risk ECL Movement', 'ECL Movement'), ('DocType', 'Credit Risk Calibration Run', 'Calibration Run')]), ('🧪 Model risk', [('DocType', 'Credit Risk Portfolio Stress Run', 'Stress Run'), ('DocType', 'Credit Risk Model Validation Run', 'Model Validation'), ('DocType', 'Credit Risk Backtest Dataset', 'Backtest Dataset')]), ('🛡️ Governance', [('Report', 'Governance Overview', 'Governance Overview')])]

_REMOVED_SECTIONS = [
	(
		"📊 Dashboards & Mobile",
		[
			("Page", "rk-executive-dashboard", "Executive Dashboard"),
			("Page", "rk-van-sales-pwa", "Van Sales PWA"),
		],
	),
	(
		"🏢 Organization & Network",
		[
			("DocType", "Omnexa Sales Settings", "Sales Settings"),
			("DocType", "Customer Profile", "Customer Profile"),
			("DocType", "Customer", "Customer"),
			("DocType", "Distribution Zone", "Distribution Zone"),
			("DocType", "Credit Risk Vehicle", "Credit Risk Vehicle"),
			("DocType", "Credit Risk Sales Representative", "Sales Representative"),
		],
	),
	(
		"🚚 Field Sales & Distribution",
		[
			("DocType", "Credit Risk Route Plan", "Route Plan"),
			("DocType", "Credit Risk Distribution Order", "Distribution Order"),
			("DocType", "Credit Risk Van Sales Invoice", "Van Sales Invoice"),
			("DocType", "Credit Risk Vehicle Stock Transfer", "Vehicle Stock Transfer"),
		],
	),
	(
		"💰 Commissions & Incentives",
		[
			("DocType", "Credit Risk Commission Rule", "Commission Rule"),
			("DocType", "Credit Risk Commission Settlement", "Commission Settlement"),
		],
	),
	(
		"📋 Tenders & Credit",
		[
			("DocType", "Credit Risk Tender", "Tender"),
			("DocType", "Credit Risk Installment Contract", "Installment Contract"),
		],
	),
	(
		"💳 Finance & ERP",
		[
			("DocType", "Sales Invoice", "Sales Invoice"),
			("DocType", "Payment Entry", "Payment Entry"),
			("DocType", "Journal Entry", "Journal Entry"),
			("DocType", "GL Account", "GL Account"),
			("DocType", "Cost Center", "Cost Center"),
		],
	),
	(
		"📈 Reports · Sales & Routes",
		[
			("Report", "Credit Risk Sales Summary", "Sales Summary"),
			("Report", "Credit Risk Distribution Fulfillment", "Distribution Fulfillment"),
			("Report", "Credit Risk Vehicle Transfer Summary", "Vehicle Transfer Summary"),
			("Report", "Credit Risk Route Efficiency", "Route Efficiency"),
			("Report", "Credit Risk Rep Target Tracking", "Rep Target Tracking"),
		],
	),
	(
		"📈 Reports · Commissions & Pipeline",
		[
			("Report", "Credit Risk Commission Summary", "Commission Summary"),
			("Report", "Credit Risk Tender Pipeline", "Tender Pipeline"),
			("Report", "Credit Risk Installment Portfolio", "Installment Portfolio"),
		],
	),
	(
		"📈 Reports · Finance & POS",
		[
			("Report", "POS Z Report Reconciliation", "POS Z Reconciliation"),
			("Report", "Sales Register", "Sales Register"),
			("Report", "Customer Ledger", "Customer Ledger"),
			("Report", "General Ledger", "General Ledger"),
		],
	),
]


def _link_exists(link_type: str, link_to: str) -> bool:
	if link_type == "DocType":
		return bool(frappe.db.exists("DocType", link_to))
	if link_type == "Report":
		return bool(frappe.db.exists("Report", link_to))
	if link_type == "Page":
		return bool(frappe.db.exists("Page", link_to))
	return False


def _build_link_rows() -> list[dict]:
	return build_link_rows_for_app("omnexa_credit_risk", WORKSPACE_SECTIONS)


def _build_shortcuts(link_rows: list[dict]) -> list[dict]:
	shortcuts: list[dict] = []
	idx = 0
	priority_types = ("Page", "DocType", "Report", "Dashboard")
	links = [r for r in link_rows if r.get("type") == "Link"]
	for lt in priority_types:
		for row in links:
			if row.get("link_type") != lt:
				continue
			entry = {
				"label": row["label"],
				"link_to": row["link_to"],
				"type": row["link_type"],
				"color": _SHORTCUT_COLORS[idx % len(_SHORTCUT_COLORS)]
	}
			if lt == "DocType":
				entry["doc_view"] = "List"
			if lt == "Report" and row.get("report_ref_doctype"):
				entry["report_ref_doctype"] = row["report_ref_doctype"]
			shortcuts.append(entry)
			idx += 1
	return shortcuts


def _onboarding_blocks(existing_content: str | None) -> list[dict]:
	if not existing_content:
		return []
	try:
		blocks = json.loads(existing_content)
	except json.JSONDecodeError:
		return []
	return [b for b in blocks if b.get("type") == "onboarding"]


def _build_content(link_rows: list[dict], ws) -> str:
	content: list[dict] = []
	content.extend(_onboarding_blocks(ws.content))
	content.append(
		{
			"id": "rk-title",
			"type": "header",
			"data": {"text": '<span class="h4"><b>Credit Risk</b></span>', "col": 12}
	}
	)
	section_idx = 0
	link_idx = 0
	for row in link_rows:
		if row.get("type") == "Card Break":
			if section_idx:
				content.append({"id": f"rk-sp-{section_idx
	}", "type": "spacer", "data": {"col": 12}
	})
			content.append(
				{
					"id": f"rk-sec-{section_idx
	}",
					"type": "header",
					"data": {"text": f'<span class="h5"><b>{row["label"]
	}</b></span>', "col": 12}
	}
			)
			section_idx += 1
			continue
		content.append(
			{
				"id": f"rk-lnk-{link_idx
	}",
				"type": "shortcut",
				"data": {"shortcut_name": row["label"], "col": 4}
	}
		)
		link_idx += 1

	if ws.number_cards:
		content.append({"id": "rk-kpi-sp", "type": "spacer", "data": {"col": 12}
	})
		content.append(
			{
				"id": "rk-kpi-h",
				"type": "header",
				"data": {"text": '<span class="h5"><b>📊 KPIs</b></span>', "col": 12}
	}
		)
		for idx, nc in enumerate(ws.number_cards):
			content.append(
				{
					"id": f"rk-nc-{idx
	}",
					"type": "number_card",
					"data": {"number_card_name": nc.number_card_name, "col": 4}
	}
			)

	if ws.charts:
		content.append({"id": "rk-ch-sp", "type": "spacer", "data": {"col": 12}
	})
		content.append(
			{
				"id": "rk-ch-h",
				"type": "header",
				"data": {"text": '<span class="h5"><b>📈 Charts</b></span>', "col": 12}
	}
		)
		for idx, ch in enumerate(ws.charts):
			content.append(
				{
					"id": f"rk-ch-{idx
	}",
					"type": "chart",
					"data": {"chart_name": ch.label or ch.chart_name, "col": 4}
	}
			)

	return json.dumps(content, separators=(",", ":"))


def sync_rk_workspace_menu(*, save: bool = True, rebuild: bool = True) -> dict:
	stats = {"sections": 0, "links": 0, "shortcuts": 0
	}
	if not frappe.db.exists("Workspace", WORKSPACE_NAME):
		return stats
	rows = _build_link_rows()
	link_rows = [r for r in rows if r.get("type") == "Link"]
	new_shortcuts = _build_shortcuts(rows)
	ws = frappe.get_doc("Workspace", WORKSPACE_NAME)
	if rebuild:
		ws.set("links", [])
		ws.set("shortcuts", [])
	for row in rows:
		if row["type"] == "Card Break":
			stats["sections"] += 1
		else:
			stats["links"] += 1
		ws.append("links", row)
	for sc in new_shortcuts:
		ws.append("shortcuts", sc)
	stats["shortcuts"] = len(new_shortcuts)
	drop_missing_workspace_dashboard_links(ws)
	ws.content = _build_content(rows, ws)
	stats["content_blocks"] = len(json.loads(ws.content))
	if save:
		ws.flags.ignore_permissions = True
		ws.flags.ignore_version = True
		latest = frappe.db.get_value("Workspace", WORKSPACE_NAME, "modified")
		if latest:
			ws._original_modified = latest
		ws.save()
		frappe.clear_cache(doctype="Workspace")
	stats["total_links"] = len(link_rows)
	return stats


@frappe.whitelist()
def get_workspace_coverage() -> dict:
	rows = _build_link_rows()
	link_rows = [r for r in rows if r.get("type") == "Link"]
	return {
		"sections": len([r for r in rows if r.get("type") == "Card Break"]),
		"links_catalogued": len(link_rows)
	}
