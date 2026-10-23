"""Window advisors helpers for MainWindow; GUI rules stay in the backend."""
from __future__ import annotations

from typing import TYPE_CHECKING
import json
from pathlib import Path
from typing import Any
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QListWidgetItem, QMessageBox
from starsector_variant_generator import api
from starsector_variant_generator.analysis.fleet_support import FleetSupportConstraints, SupportFocus, fleet_support_request_from_payload, fleet_support_request_to_payload, parse_fleet_selections
from starsector_variant_generator.analysis.scenario_advisor import ScenarioCapabilityTarget, generic_scenario_profiles, scenario_advisor_request_from_payload, scenario_advisor_request_to_payload, user_defined_scenario
from starsector_variant_generator.core.safeio import atomic_write_text
from starsector_variant_generator.gui.presentation import format_fleet_support_comparison, format_fleet_support_result, format_fleet_support_why_not, format_generation_results, format_scenario_fleet_assessment

if TYPE_CHECKING:
    from .main_window import MainWindow


def _fleet_support(self: MainWindow) -> None:
    if self._registry is None:
        self.faction_detail.setPlainText("Scan an installation before asking for fleet support advice."); return
    hull_ids = tuple(item.strip() for item in self.fleet_support_hulls.text().split(",") if item.strip())
    if not hull_ids:
        self.faction_detail.setPlainText("Enter at least one locked hull ID. Repeating an ID records another selected ship."); return
    try:
        selections = parse_fleet_selections(hull_ids)
    except ValueError as exc:
        self.faction_detail.setPlainText(str(exc)); return
    selected = self._faction_id()
    access = str(self.fleet_support_access.currentData())
    if access == "STRICT_FACTION" and selected is None:
        QMessageBox.information(self, "Faction required", "Select a faction before using Strict Faction access."); return
    heuristic_set = str(self.fleet_support_heuristic.currentData())
    constraints = FleetSupportConstraints(access_mode=access, allow_foreign_hulls=self.fleet_support_allow_foreign.isChecked(), include_hidden_hulls=self.fleet_support_include_hidden.isChecked(), focus=SupportFocus(str(self.fleet_support_focus.currentData())))
    faction_id, source_mod = selected if selected is not None else (None, None)
    self._run("Analyzing locked fleet selections and ranking individual additions…", lambda: api.run_fleet_support_advisor(self._registry, selections, faction_id, source_mod, heuristic_set, constraints), self._show_fleet_support_result, self.fleet_support_button)


def _show_fleet_support_result(self: MainWindow, result: Any) -> None:
    self._fleet_support_last_result = result
    self._advisor_card_origin = "FLEET_SUPPORT"
    self.faction_detail.setPlainText(format_fleet_support_result(result))
    self.fleet_support_cards.clear()
    for item in result.recommendations:
        purposes = ", ".join(item.support_purposes) or "support addition"
        card = QListWidgetItem(f"{item.hull_id}  •  {purposes}  •  score {item.recommendation_score:.3f}")
        card.setData(Qt.UserRole, item.hull_id)
        composition = item.score_components.composition_synergy if item.score_components is not None else None
        card.setToolTip(f"Supports: {', '.join(item.supports)}\nComposition synergy: {composition:.3f}" if composition is not None else f"Supports: {', '.join(item.supports)}\n{item.diversity_reason or 'Selected by score.'}")
        self.fleet_support_cards.addItem(card)
    if not result.recommendations:
        self.fleet_support_cards.addItem("No material candidate additions.")


def _scenario_profile_from_controls(self: MainWindow) -> Any:
    selected = str(self.scenario_profile.currentData())
    if selected != "CUSTOM":
        return next(profile for profile in generic_scenario_profiles() if profile.scenario_id == selected)
    targets: list[ScenarioCapabilityTarget] = []
    for token in self.scenario_targets.text().split(","):
        name, separator, value = token.strip().partition("=")
        if not separator:
            raise ValueError("Custom scenario targets use CAPABILITY=0.00 through CAPABILITY=1.00")
        try:
            targets.append(ScenarioCapabilityTarget(name.strip().upper(), float(value.strip())))
        except ValueError as exc:
            raise ValueError(f"Invalid target value for {name.strip() or 'capability'}") from exc
    return user_defined_scenario("custom_declared", "Custom Declared Scenario", tuple(targets))


def _evaluate_scenario(self: MainWindow) -> None:
    if self._registry is None:
        self.faction_detail.setPlainText("Scan an installation before evaluating a scenario."); return
    tokens = tuple(item.strip() for item in self.fleet_support_hulls.text().split(",") if item.strip())
    if not tokens:
        self.faction_detail.setPlainText("Enter at least one locked hull ID before evaluating a scenario."); return
    try:
        selections = parse_fleet_selections(tokens); scenario = self._scenario_profile_from_controls()
    except ValueError as exc:
        self.faction_detail.setPlainText(str(exc)); return
    selected = self._faction_id(); constraints = self._fleet_support_constraints_from_controls()
    if constraints.access_mode == "STRICT_FACTION" and selected is None:
        QMessageBox.information(self, "Faction required", "Select a faction before using Strict Faction access."); return
    faction_id, source_mod = selected if selected is not None else (None, None)
    heuristic_set = str(self.fleet_support_heuristic.currentData())
    def complete(result: Any) -> None:
        self._scenario_last_result = result
        self._advisor_card_origin = "SCENARIO"
        self.faction_detail.setPlainText(format_scenario_fleet_assessment(result))
        self.fleet_support_cards.clear()
        for item in result.recommendations:
            purposes = ", ".join(item.support_purposes) or "scenario support addition"
            card = QListWidgetItem(f"{item.hull_id} - {purposes} - scenario score {item.recommendation_score:.3f}")
            card.setData(Qt.UserRole, item.hull_id)
            card.setToolTip("Scenario-targeted addition. Revalidate before generating a concrete fit.\nSupports: " + ", ".join(item.supports))
            self.fleet_support_cards.addItem(card)
        if not result.recommendations:
            self.fleet_support_cards.addItem("No material scenario-targeted additions.")
    self._run("Comparing locked fleet mechanics with declared scenario targets", lambda: api.run_scenario_fleet_advisor(self._registry, selections, scenario, faction_id, source_mod, heuristic_set, constraints), complete, self.scenario_evaluate_button, cancellable=True)


def _generate_scenario_fit(self: MainWindow) -> None:
    if self._registry is None:
        self.faction_detail.setPlainText("Scan an installation before generating a scenario fit."); return
    candidate = self.fleet_support_candidate.text().strip()
    tokens = tuple(item.strip() for item in self.fleet_support_hulls.text().split(",") if item.strip())
    if not candidate or not tokens:
        self.faction_detail.setPlainText("Select a current scenario recommendation and keep at least one locked hull ID."); return
    try:
        selections = parse_fleet_selections(tokens); scenario = self._scenario_profile_from_controls()
    except ValueError as exc:
        self.faction_detail.setPlainText(str(exc)); return
    selected = self._faction_id(); constraints = self._fleet_support_constraints_from_controls()
    if constraints.access_mode == "STRICT_FACTION" and selected is None:
        QMessageBox.information(self, "Faction required", "Select a faction before using Strict Faction access."); return
    faction_id, source_mod = selected if selected is not None else (None, None)
    heuristic_set = str(self.fleet_support_heuristic.currentData())
    def complete(outcome: Any) -> None:
        self.faction_detail.setPlainText(
            f"SCENARIO SUPPORT FIT - {outcome.recommendation.hull_id}\n"
            f"Scenario: {outcome.assessment.scenario.display_name}\nPurpose: {outcome.support_purpose}\n"
            f"Generator profile: {outcome.generator_profile}\n\n"
            + format_generation_results(outcome.generation.assessed_candidates, outcome.generation.selected_profile, outcome.generation.flux_mode)
        )
    self._run("Revalidating scenario recommendation and generating a concrete fit", lambda: api.run_generate_scenario_support_fit(self._registry, selections, scenario, candidate, faction_id, source_mod, heuristic_set, constraints), complete, self.generate_scenario_fit_button, cancellable=True)


def _save_scenario_request(self: MainWindow) -> None:
    tokens = tuple(item.strip() for item in self.fleet_support_hulls.text().split(",") if item.strip())
    try:
        selections = parse_fleet_selections(tokens); scenario = self._scenario_profile_from_controls()
    except ValueError as exc:
        self.faction_detail.setPlainText(str(exc)); return
    path, _ = QFileDialog.getSaveFileName(self, "Save Scenario Advisor Request", "scenario-advisor-request.json", "JSON files (*.json)")
    if not path:
        return
    try:
        atomic_write_text(Path(path), json.dumps(scenario_advisor_request_to_payload(selections, scenario, self._fleet_support_constraints_from_controls()), indent=2))
    except OSError as exc:
        QMessageBox.warning(self, "Request not saved", str(exc)); return
    self.statusBar().showMessage("Scenario Advisor request saved; it contains only declared selections, targets, and constraints.")


def _load_scenario_request(self: MainWindow) -> None:
    path, _ = QFileDialog.getOpenFileName(self, "Load Scenario Advisor Request", "", "JSON files (*.json)")
    if not path:
        return
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        selections, scenario, constraints = scenario_advisor_request_from_payload(payload)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        QMessageBox.warning(self, "Request not loaded", str(exc)); return
    entries = [(f"variant:{item.variant_id}" if item.variant_id else str(item.hull_id)) + (f"*{item.count}" if item.count != 1 else "") for item in selections]
    self.fleet_support_hulls.setText(", ".join(entries))
    profile_index = self.scenario_profile.findData(scenario.scenario_id)
    if profile_index >= 0:
        self.scenario_profile.setCurrentIndex(profile_index); self.scenario_targets.clear()
    else:
        self.scenario_profile.setCurrentIndex(self.scenario_profile.findData("CUSTOM"))
        self.scenario_targets.setText(", ".join(f"{item.capability}={item.target:.2f}" for item in scenario.capability_targets))
    self.fleet_support_focus.setCurrentIndex(max(0, self.fleet_support_focus.findData(constraints.focus.value)))
    self.fleet_support_access.setCurrentIndex(max(0, self.fleet_support_access.findData(constraints.access_mode)))
    self.fleet_support_allow_foreign.setChecked(constraints.allow_foreign_hulls)
    self.fleet_support_include_hidden.setChecked(constraints.include_hidden_hulls)
    self.statusBar().showMessage("Scenario Advisor request loaded; scan local data before evaluating it.")


def _compare_fleet_support_cards(self: MainWindow) -> None:
    result = getattr(self, "_scenario_last_result", None) if self._advisor_card_origin == "SCENARIO" else getattr(self, "_fleet_support_last_result", None)
    by_id = {item.hull_id: item for item in getattr(result, "recommendations", ())}
    selected = tuple(by_id[item.data(Qt.UserRole)] for item in self.fleet_support_cards.selectedItems() if isinstance(item.data(Qt.UserRole), str) and item.data(Qt.UserRole) in by_id)
    if len(selected) < 2:
        self.faction_detail.setPlainText("Select at least two recommendation cards to compare their backend evidence."); return
    self.faction_detail.setPlainText(format_fleet_support_comparison(selected))


def _fleet_support_card_selected(self: MainWindow, _: int) -> None:
    item = self.fleet_support_cards.currentItem()
    hull_id = item.data(Qt.UserRole) if item is not None else None
    if isinstance(hull_id, str):
        self.fleet_support_candidate.setText(hull_id)


def _generate_support_fit(self: MainWindow) -> None:
    if self._registry is None:
        self.faction_detail.setPlainText("Scan an installation before generating a support fit."); return
    if self._advisor_card_origin == "SCENARIO":
        self.faction_detail.setPlainText("These cards came from Scenario Advisor. Use Generate Scenario Fit so the declared scenario targets are revalidated."); return
    candidate = self.fleet_support_candidate.text().strip()
    tokens = tuple(item.strip() for item in self.fleet_support_hulls.text().split(",") if item.strip())
    if not candidate or not tokens:
        self.faction_detail.setPlainText("Select a current support recommendation and keep at least one locked hull ID."); return
    try:
        selections = parse_fleet_selections(tokens)
    except ValueError as exc:
        self.faction_detail.setPlainText(str(exc)); return
    selected = self._faction_id(); constraints = self._fleet_support_constraints_from_controls()
    if constraints.access_mode == "STRICT_FACTION" and selected is None:
        QMessageBox.information(self, "Faction required", "Select a faction before using Strict Faction access."); return
    faction_id, source_mod = selected if selected is not None else (None, None)
    heuristic_set = str(self.fleet_support_heuristic.currentData())
    def complete(outcome: Any) -> None:
        self.faction_detail.setPlainText(f"SUPPORT FIT — {outcome.recommendation.hull_id}\nPurpose: {outcome.support_purpose}\nGenerator profile: {outcome.generator_profile}\n\n" + format_generation_results(outcome.generation.assessed_candidates, outcome.generation.selected_profile, outcome.generation.flux_mode))
    self._run("Revalidating advisor recommendation and generating a concrete support fit…", lambda: api.run_generate_fleet_support_fit(self._registry, selections, candidate, faction_id, source_mod, heuristic_set, constraints), complete, self.generate_support_fit_button)


def _add_current_hull_to_fleet_support(self: MainWindow) -> None:
    if self._current_hull is None:
        return
    current = [item.strip() for item in self.fleet_support_hulls.text().split(",") if item.strip()]
    current.append(self._current_hull.id)
    self.fleet_support_hulls.setText(", ".join(current))
    self.workspace_tabs.setCurrentIndex(2)
    self.fleet_support_hulls.setFocus()
    self.statusBar().showMessage(f"Added {self._current_hull.id} as a locked Fleet Support Advisor selection.")


def _clear_fleet_support(self: MainWindow) -> None:
    self.fleet_support_hulls.clear()
    self.fleet_support_candidate.clear()
    self.faction_detail.setPlainText("Fleet Support Advisor selection cleared. Enter locked hull IDs or add one from Ships.")
    self.statusBar().showMessage("Fleet Support Advisor local selection cleared.")


def _fleet_support_constraints_from_controls(self: MainWindow) -> FleetSupportConstraints:
    return FleetSupportConstraints(
        access_mode=str(self.fleet_support_access.currentData()),
        allow_foreign_hulls=self.fleet_support_allow_foreign.isChecked(),
        include_hidden_hulls=self.fleet_support_include_hidden.isChecked(),
        focus=SupportFocus(str(self.fleet_support_focus.currentData())),
    )


def _save_fleet_support_request(self: MainWindow) -> None:
    tokens = tuple(item.strip() for item in self.fleet_support_hulls.text().split(",") if item.strip())
    try:
        selections = parse_fleet_selections(tokens)
    except ValueError as exc:
        self.faction_detail.setPlainText(str(exc)); return
    path, _ = QFileDialog.getSaveFileName(self, "Save Fleet Support Request", "fleet-support-request.json", "JSON files (*.json)")
    if not path:
        return
    try:
        atomic_write_text(Path(path), json.dumps(fleet_support_request_to_payload(selections, self._fleet_support_constraints_from_controls()), indent=2))
    except OSError as exc:
        QMessageBox.warning(self, "Request not saved", str(exc)); return
    self.statusBar().showMessage("Fleet Support Advisor request saved.")


def _load_fleet_support_request(self: MainWindow) -> None:
    path, _ = QFileDialog.getOpenFileName(self, "Load Fleet Support Request", "", "JSON files (*.json)")
    if not path:
        return
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        selections, constraints = fleet_support_request_from_payload(payload)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        QMessageBox.warning(self, "Request not loaded", str(exc)); return
    entries = []
    for item in selections:
        identifier = f"variant:{item.variant_id}" if item.variant_id else str(item.hull_id)
        entries.append(f"{identifier}*{item.count}" if item.count != 1 else identifier)
    self.fleet_support_hulls.setText(", ".join(entries))
    self.fleet_support_focus.setCurrentIndex(max(0, self.fleet_support_focus.findData(constraints.focus.value)))
    self.fleet_support_access.setCurrentIndex(max(0, self.fleet_support_access.findData(constraints.access_mode)))
    self.fleet_support_allow_foreign.setChecked(constraints.allow_foreign_hulls)
    self.fleet_support_include_hidden.setChecked(constraints.include_hidden_hulls)
    self.statusBar().showMessage("Fleet Support Advisor request loaded.")


def _fleet_support_why_not(self: MainWindow) -> None:
    if self._registry is None:
        self.faction_detail.setPlainText("Scan an installation before asking for a Fleet Support Why-Not explanation."); return
    candidate = self.fleet_support_candidate.text().strip()
    hull_ids = tuple(item.strip() for item in self.fleet_support_hulls.text().split(",") if item.strip())
    if not candidate or not hull_ids:
        self.faction_detail.setPlainText("Enter both a candidate hull ID and at least one locked hull ID."); return
    try:
        selections = parse_fleet_selections(hull_ids)
    except ValueError as exc:
        self.faction_detail.setPlainText(str(exc)); return
    selected = self._faction_id(); access = str(self.fleet_support_access.currentData())
    if access == "STRICT_FACTION" and selected is None:
        QMessageBox.information(self, "Faction required", "Select a faction before using Strict Faction access."); return
    heuristic_set = str(self.fleet_support_heuristic.currentData())
    constraints = FleetSupportConstraints(access_mode=access, allow_foreign_hulls=self.fleet_support_allow_foreign.isChecked(), include_hidden_hulls=self.fleet_support_include_hidden.isChecked(), focus=SupportFocus(str(self.fleet_support_focus.currentData())))
    faction_id, source_mod = selected if selected is not None else (None, None)
    self._run("Explaining Fleet Support Advisor candidate…", lambda: api.run_fleet_support_why_not(self._registry, selections, candidate, faction_id, source_mod, heuristic_set, constraints), lambda result: self.faction_detail.setPlainText(format_fleet_support_why_not(result)), self.fleet_support_why_not_button)
