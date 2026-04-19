# Copyright (c) 2026, Omnexa and contributors
# License: MIT. See license.txt

from __future__ import annotations


def get_standards_profile() -> dict:
	"""International standards posture for omnexa_credit_risk."""
	return {
		"app": "omnexa_credit_risk",
		"standards": ['IFRS', 'IFRS9', 'BASEL_III_IV', 'GAAP', 'ISO_27001', 'ISO_20022', 'SOX'],
		"activity_controls": ['pd-lgd-ead', 'stress-testing', 'portfolio-risk-aggregation', 'basel-capital'],
		"multi_country_ready": True,
		"auditability": "high",
		"api_contract_version": "v1",
	}
