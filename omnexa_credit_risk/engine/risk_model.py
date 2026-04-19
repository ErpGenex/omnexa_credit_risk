# Copyright (c) 2026, Omnexa and contributors
# License: MIT. See license.txt

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ExposurePoint:
	segment: str
	pd: Decimal  # Probability of default (0..1)
	lgd: Decimal  # Loss given default (0..1)
	ead: Decimal  # Exposure at default (currency)


@dataclass(frozen=True)
class AccountExposurePoint:
	account_id: str
	segment: str
	pd: Decimal
	lgd: Decimal
	ead: Decimal
	dpd: int = 0
	sicr_flag: bool = False
	default_flag: bool = False
	country_code: str = "INTL"
	product_code: str = "GENERIC"


@dataclass(frozen=True)
class StressScenario:
	name: str
	pd_multiplier: Decimal = Decimal("1.0")
	lgd_multiplier: Decimal = Decimal("1.0")
	ead_multiplier: Decimal = Decimal("1.0")
	floor_pd: Decimal = Decimal("0.0")
	cap_pd: Decimal = Decimal("1.0")
	floor_lgd: Decimal = Decimal("0.0")
	cap_lgd: Decimal = Decimal("1.0")


@dataclass(frozen=True)
class MacroeconomicOverlay:
	name: str
	pd_addon: Decimal = Decimal("0.0")
	lgd_addon: Decimal = Decimal("0.0")
	ead_addon_multiplier: Decimal = Decimal("0.0")


@dataclass(frozen=True)
class Ifrs9StageResult:
	segment: str
	stage: str  # STAGE_1 | STAGE_2 | STAGE_3
	provision_rate: Decimal
	provision_amount: Decimal


@dataclass(frozen=True)
class AccountRiskResult:
	account_id: str
	segment: str
	stage: str
	pd: Decimal
	lgd: Decimal
	ead: Decimal
	ecl: Decimal
	provision_rate: Decimal
	provision_amount: Decimal
	country_code: str
	product_code: str


@dataclass(frozen=True)
class BacktestPoint:
	account_id: str
	predicted_pd: Decimal
	observed_default: int  # 0/1


@dataclass(frozen=True)
class ModelValidationResult:
	total_accounts: int
	observed_default_rate: Decimal
	average_predicted_pd: Decimal
	brier_score: Decimal
	accuracy_band: str  # STRONG | ACCEPTABLE | WEAK


def calculate_expected_loss(points: list[ExposurePoint]) -> Decimal:
	"""Basel/IFRS9-style baseline EL = sum(PD * LGD * EAD)."""
	_validate_points(points)
	total = Decimal("0")
	for p in points:
		total += p.pd * p.lgd * p.ead
	return total


def calculate_account_level_ecl(points: list[AccountExposurePoint], overlay: MacroeconomicOverlay | None = None) -> list[AccountRiskResult]:
	_validate_account_points(points)
	out: list[AccountRiskResult] = []
	for p in points:
		pd = p.pd
		lgd = p.lgd
		ead = p.ead
		if overlay:
			pd = _bounded(pd + overlay.pd_addon, Decimal("0"), Decimal("1"))
			lgd = _bounded(lgd + overlay.lgd_addon, Decimal("0"), Decimal("1"))
			ead = ead * (Decimal("1") + overlay.ead_addon_multiplier)
		stage = allocate_ifrs9_stage_account(dpd=p.dpd, sicr_flag=p.sicr_flag, default_flag=p.default_flag)
		if stage == "STAGE_1":
			rate = pd * lgd
		elif stage == "STAGE_2":
			rate = (pd * Decimal("1.5")) * lgd
		else:
			rate = lgd
		ecl = pd * lgd * ead
		out.append(
			AccountRiskResult(
				account_id=p.account_id,
				segment=p.segment,
				stage=stage,
				pd=pd,
				lgd=lgd,
				ead=ead,
				ecl=ecl,
				provision_rate=rate,
				provision_amount=rate * ead,
				country_code=p.country_code,
				product_code=p.product_code,
			)
		)
	return out


def aggregate_portfolio_view(results: list[AccountRiskResult]) -> dict:
	total_ecl = sum((r.ecl for r in results), Decimal("0"))
	total_provision = sum((r.provision_amount for r in results), Decimal("0"))
	stage_breakdown = {
		"STAGE_1": sum((r.provision_amount for r in results if r.stage == "STAGE_1"), Decimal("0")),
		"STAGE_2": sum((r.provision_amount for r in results if r.stage == "STAGE_2"), Decimal("0")),
		"STAGE_3": sum((r.provision_amount for r in results if r.stage == "STAGE_3"), Decimal("0")),
	}
	return {
		"accounts_count": len(results),
		"total_ecl": total_ecl,
		"total_provision": total_provision,
		"stage_breakdown": stage_breakdown,
	}


def stress_expected_loss(points: list[ExposurePoint], scenario: StressScenario) -> tuple[Decimal, list[ExposurePoint]]:
	"""Apply stress multipliers/floors/caps then compute stressed EL."""
	_validate_points(points)
	stressed: list[ExposurePoint] = []
	for p in points:
		pd = _bounded(p.pd * scenario.pd_multiplier, scenario.floor_pd, scenario.cap_pd)
		lgd = _bounded(p.lgd * scenario.lgd_multiplier, scenario.floor_lgd, scenario.cap_lgd)
		ead = p.ead * scenario.ead_multiplier
		stressed.append(ExposurePoint(segment=p.segment, pd=pd, lgd=lgd, ead=ead))
	return calculate_expected_loss(stressed), stressed


def _bounded(v: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
	if v < lo:
		return lo
	if v > hi:
		return hi
	return v


def _validate_points(points: list[ExposurePoint]) -> None:
	if not points:
		raise ValueError("At least one exposure point is required")
	for p in points:
		if p.ead < 0:
			raise ValueError("EAD must be non-negative")
		if p.pd < 0 or p.pd > 1:
			raise ValueError("PD must be within [0, 1]")
		if p.lgd < 0 or p.lgd > 1:
			raise ValueError("LGD must be within [0, 1]")


def allocate_ifrs9_stage(pd: Decimal, default_flag: bool = False) -> str:
	"""
	Baseline IFRS9 staging:
	- stage 3: defaulted exposure
	- stage 2: significant increase in credit risk proxy (pd >= 10%)
	- stage 1: otherwise
	"""
	if default_flag:
		return "STAGE_3"
	if pd >= Decimal("0.10"):
		return "STAGE_2"
	return "STAGE_1"


def allocate_ifrs9_stage_account(dpd: int = 0, sicr_flag: bool = False, default_flag: bool = False) -> str:
	"""
	IFRS9 staging proxy:
	- STAGE_3: default_flag OR DPD >= 90
	- STAGE_2: SICR flag OR DPD >= 30
	- STAGE_1: otherwise
	"""
	if default_flag or dpd >= 90:
		return "STAGE_3"
	if sicr_flag or dpd >= 30:
		return "STAGE_2"
	return "STAGE_1"


def calculate_ifrs9_provisions(points: list[ExposurePoint], defaulted_segments: set[str] | None = None) -> list[Ifrs9StageResult]:
	"""Compute per-segment stage and baseline provision amount."""
	_validate_points(points)
	defaulted = defaulted_segments or set()
	out: list[Ifrs9StageResult] = []
	for p in points:
		stage = allocate_ifrs9_stage(pd=p.pd, default_flag=(p.segment in defaulted))
		if stage == "STAGE_1":
			rate = p.pd * p.lgd
		elif stage == "STAGE_2":
			rate = (p.pd * Decimal("1.5")) * p.lgd
		else:
			rate = p.lgd
		out.append(
			Ifrs9StageResult(
				segment=p.segment,
				stage=stage,
				provision_rate=rate,
				provision_amount=rate * p.ead,
			)
		)
	return out


def run_backtesting(points: list[BacktestPoint]) -> ModelValidationResult:
	if not points:
		raise ValueError("At least one backtest point is required")
	n = Decimal(len(points))
	observed_rate = sum((Decimal(p.observed_default) for p in points), Decimal("0")) / n
	avg_pd = sum((p.predicted_pd for p in points), Decimal("0")) / n
	brier = sum(((p.predicted_pd - Decimal(p.observed_default)) ** Decimal("2") for p in points), Decimal("0")) / n
	if brier <= Decimal("0.10"):
		band = "STRONG"
	elif brier <= Decimal("0.20"):
		band = "ACCEPTABLE"
	else:
		band = "WEAK"
	return ModelValidationResult(
		total_accounts=int(n),
		observed_default_rate=observed_rate,
		average_predicted_pd=avg_pd,
		brier_score=brier,
		accuracy_band=band,
	)


def _validate_account_points(points: list[AccountExposurePoint]) -> None:
	if not points:
		raise ValueError("At least one account exposure point is required")
	for p in points:
		if p.ead < 0:
			raise ValueError("EAD must be non-negative")
		if p.pd < 0 or p.pd > 1:
			raise ValueError("PD must be within [0, 1]")
		if p.lgd < 0 or p.lgd > 1:
			raise ValueError("LGD must be within [0, 1]")
		if p.dpd < 0:
			raise ValueError("DPD must be non-negative")

