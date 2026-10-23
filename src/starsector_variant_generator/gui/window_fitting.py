"""Window fitting helpers for MainWindow; GUI rules stay in the backend."""
from __future__ import annotations

from typing import TYPE_CHECKING
from collections.abc import Callable
from pathlib import Path
from typing import Any
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QInputDialog, QLineEdit, QListWidgetItem, QMessageBox, QPushButton
from starsector_variant_generator import api
from starsector_variant_generator.core.config import DEFAULT_HEURISTIC_SET
from starsector_variant_generator.core.models import Variant
from starsector_variant_generator.gui.canvas import _detect_mirror_mount_pairs, _displayable_weapon_mounts
from starsector_variant_generator.gui.models import EntityTableModel
from starsector_variant_generator.gui.presentation import format_generation_results

if TYPE_CHECKING:
    from .main_window import MainWindow


def _refresh_hulls(self: MainWindow) -> None:
    if self._catalog is None: return
    self._visible = self._catalog.filter(self.search.text(), self.size_filter.currentData(), self.source_filter.currentData(), self.faction_filter.currentData()); self.hull_list.blockSignals(True); self.hull_list.clear()
    for hull in self._visible:
        # A real, blank hull.name is not unusual -- confirmed on a live
        # install: many modded composite-hull sub-modules (e.g. a boss
        # ship's individual turret pieces) genuinely declare no display
        # name at all, since they're never shown standalone in-game.
        # Falling back to the real hull id keeps every row distinguishable
        # instead of many identical "<size> • <source_mod>" rows.
        affiliations = ", ".join(self._catalog.faction_labels_for(hull)) or "No parsed faction"
        item = QListWidgetItem(f"{hull.name or hull.id}\n{hull.hull_size or 'Unknown'} • {hull.source_mod} • {affiliations}"); item.setData(Qt.UserRole, hull.id); self.hull_list.addItem(item)
    self.hull_list.blockSignals(False); self.count.setText(f"HULLS ({len(self._visible)})"); self.hull_list.setCurrentRow(0 if self._visible else -1)


def _schedule_hull_refresh(self: MainWindow) -> None:
    """Avoid rebuilding a large hull list once per keystroke."""
    self._hull_filter_timer.start()


def _reset_filters(self: MainWindow) -> None: self.search.clear(); self.size_filter.setCurrentIndex(0); self.source_filter.setCurrentIndex(0); self.faction_filter.setCurrentIndex(0)


def _show_provenance(self: MainWindow, category: str) -> None:
    table = self.data_tables[category]; row = table.currentIndex().row()
    model = table.model()
    if not isinstance(model, EntityTableModel) or row < 0 or row >= len(model.entities): return
    entity = model.entities[row]
    lines = [
        f"ID: {entity.id}", f"Name: {entity.name}", f"Source mod: {entity.source_mod}",
        f"Source file: {entity.source_path}", f"Source hash: {entity.source_hash or 'Unavailable'}",
        f"Source mod version: {entity.source_mod_version or 'Unavailable'}",
    ]
    if category == "Variants":
        lines.append(f"Parent hull: {entity.hull_id or 'Unavailable'}")
        if isinstance(entity.raw.get("modules"), list) and entity.raw["modules"]:
            lines.append("Complex module mappings: retained as provenance only; not compositely analyzed.")
    self.provenance_detail.setPlainText("\n".join(lines))


def _open_variant_hull(self: MainWindow, item: QListWidgetItem) -> None:
    if self._registry is None: return
    variant = self._registry.variants.by_id.get(str(item.data(Qt.UserRole)))
    if variant is not None:
        self._open_retrofit_variant(variant)


def _open_retrofit_variant(self: MainWindow, variant: Variant) -> None:
    if self._registry is None:
        return
    hull = self._registry.hulls.by_id.get(variant.hull_id) if variant and variant.hull_id else None
    if hull is None:
        self.refit_detail.setPlainText("The variant parent hull is missing or ambiguous; it cannot be opened safely.")
        return
    self.workspace_tabs.setCurrentIndex(0); self.ship_tabs.setCurrentIndex(0)
    try: self.hull_list.setCurrentRow(self._visible.index(hull))
    except ValueError:
        self.search.clear(); self.size_filter.setCurrentIndex(0); self.source_filter.setCurrentIndex(0); self.faction_filter.setCurrentIndex(0); self._refresh_hulls(); self.hull_list.setCurrentRow(self._visible.index(hull))
    self._loaded_retrofit_variant = variant
    self._fit_weapons = {**hull.built_in_weapons, **variant.weapons_by_mount}
    self.editable_hullmods.setText(", ".join(variant.hullmods)); self.editable_wings.setText(", ".join(variant.fighter_wings))
    self.editable_vents.setText("" if variant.flux_vents is None else str(variant.flux_vents)); self.editable_capacitors.setText("" if variant.flux_capacitors is None else str(variant.flux_capacitors))
    self._update_fit_metrics(); self.canvas.show_hull(hull, self._fit_weapons, self._registry.weapons.by_id)
    self.inspect_detail.appendPlainText(f"\nEditing existing variant: {variant.id}\nSaving creates/replaces only a local editable copy.")


def _selected_hull(self: MainWindow, row: int) -> None:
    if row < 0 or row >= len(self._visible): self.canvas.show_empty(); self.generate_button.setEnabled(False); self._mirror_pairs = {}; self.mirror_fitting.setEnabled(False); self.mirror_fitting.setChecked(False); self.mirror_fitting.setText("Mirror fitting"); self.mirror_fitting.setToolTip("No hull selected yet."); return
    hull = self._visible[row]; self._current_hull = hull; self._loaded_retrofit_variant = None; self._fit_weapons = dict(hull.built_in_weapons); self.editable_hullmods.clear(); self.editable_wings.clear(); self.editable_vents.clear(); self.editable_capacitors.clear(); self.heading.setText(hull.name or hull.id); self.subheading.setText(f"{hull.id} • {hull.source_mod}")
    data = {"Hull Size": hull.hull_size or "Unknown", "Source Mod": hull.source_mod, "OP": str(hull.ordnance_points or "Unknown"), "Weapon Mounts": str(len(_displayable_weapon_mounts(hull))), "Built-ins": str(len(hull.built_in_hullmods) + len(hull.built_in_weapons))}
    for key, value in data.items(): self.values[key].setText(value)
    self._mirror_pairs = _detect_mirror_mount_pairs(hull)
    pair_count = len(self._mirror_pairs) // 2
    self.mirror_fitting.setEnabled(pair_count > 0)
    if not pair_count: self.mirror_fitting.setChecked(False)
    self.mirror_fitting.setText(f"Mirror fitting ({pair_count} pair{'s' if pair_count != 1 else ''} detected)" if pair_count else "Mirror fitting (no symmetric pairs detected)")
    self.mirror_fitting.setToolTip("Assigning or clearing a weapon on one mount also applies it to its detected left/right mirror mount." if pair_count else "No left/right mirror-symmetric mount pairs were found in this hull's parsed geometry.")
    affiliations = ", ".join(self._catalog.faction_labels_for(hull)) if self._catalog is not None else ""
    self._update_fit_metrics(); self.canvas.show_hull(hull, self._fit_weapons, self._registry.weapons.by_id if self._registry is not None else None); self.inspect_detail.setPlainText(f"{hull.name} ({hull.id})\nSource: {hull.source_mod}\nFaction evidence: {affiliations or 'No parsed faction'}\nSelectable weapon mounts: {len(_displayable_weapon_mounts(hull))} | Launch bays: {len(hull.launch_bay_slots)} | OP: {hull.ordnance_points}"); self.generate_button.setEnabled(self._registry is not None); self.add_to_fleet_support_button.setEnabled(self._registry is not None); self.save_editable_fit_button.setEnabled(self._registry is not None)


def _update_fit_metrics(self: MainWindow) -> None:
    if self._registry is None or self._current_hull is None: return
    try:
        fit = self._editable_canvas_variant(f"gui_{self._current_hull.id}", "GUI Fit")
    except ValueError as exc:
        self.fit_metrics.setText(f"FIT STATUS: INVALID EDITABLE FIELD\n{exc}")
        return
    summary = api.run_fit_summary(self._registry, fit)
    available = summary["hull_ordnance_points"] if summary["hull_ordnance_points"] is not None else "Unknown"
    text = f"FIT STATUS: {summary['legality']}\nWeapon OP {summary['weapon_op_used']}/{available}"
    if summary["weapon_op_remaining"] is not None: text += f" (remaining {summary['weapon_op_remaining']})"
    # `run_fit_summary` (api.py) is typed `dict[str, object]`, but its
    # own construction always populates "failures"/"uncertainties" with
    # a `list[str]`; the `isinstance` guards below narrow that for the
    # type checker without changing behavior in that always-true case.
    failures, uncertainties = summary["failures"], summary["uncertainties"]
    notes = [
        *(failures if isinstance(failures, list) else []),
        *(uncertainties if isinstance(uncertainties, list) else []),
    ]
    self.fit_metrics.setText(text + (f"\n{'; '.join(notes)}" if notes else ""))


def _editable_canvas_variant(self: MainWindow, variant_id: str, name: str) -> Variant:
    if self._current_hull is None:
        raise ValueError("No hull selected.")
    loaded = self._loaded_retrofit_variant
    vents = self._editable_stat_value(self.editable_vents, loaded.flux_vents if loaded else None)
    capacitors = self._editable_stat_value(self.editable_capacitors, loaded.flux_capacitors if loaded else None)
    hullmods = tuple(item.strip() for item in self.editable_hullmods.text().split(",") if item.strip())
    wings = tuple(item.strip() for item in self.editable_wings.text().split(",") if item.strip())
    return Variant(variant_id, name, "USER_EDITABLE", self._current_hull.source_path, hull_id=self._current_hull.id, weapons_by_mount=dict(self._fit_weapons), hullmods=hullmods, fighter_wings=wings, flux_vents=vents, flux_capacitors=capacitors)


def _save_current_fit_to_library(self: MainWindow) -> None:
    if self._registry is None or self._current_hull is None:
        return
    output = self.output.text().strip()
    if not output:
        QMessageBox.warning(self, "Output directory required", "Choose an output directory before saving an editable fit."); return
    default_id = self._loaded_retrofit_variant.id if self._loaded_retrofit_variant is not None else f"{self._current_hull.id}_custom"
    variant_id, accepted = QInputDialog.getText(self, "Save editable fit", "Variant ID", text=default_id)
    if not accepted or not variant_id.strip():
        return
    try:
        fit = self._editable_canvas_variant(variant_id.strip(), variant_id.strip())
    except ValueError as exc:
        QMessageBox.warning(self, "Fit not saved", str(exc)); return
    try:
        path = api.save_editable_retrofit_variant(self._registry, fit, Path(output), replace=False)
    except FileExistsError:
        if QMessageBox.question(self, "Replace editable fit?", "A local editable fit with this ID already exists. Replace it?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        path = api.save_editable_retrofit_variant(self._registry, fit, Path(output), replace=True)
    except ValueError as exc:
        QMessageBox.warning(self, "Fit not saved", str(exc)); return
    self.statusBar().showMessage(f"Saved editable local fit: {path}")
    self._refresh_editable_retrofit_library()


def _editable_stat_value(field: QLineEdit, fallback: int | None) -> int | None:
    text = field.text().strip()
    if not text:
        return fallback
    if not text.isdecimal():
        raise ValueError("Editable flux vents/capacitors must be non-negative integers.")
    return int(text)


def _choose_slot(self: MainWindow, slot_id: str) -> None:
    if self._registry is None or self._current_hull is None: return
    faction_id = self.generation_faction_selector.currentData(); faction_mode = str(self.faction_mode_selector.currentData())
    if faction_mode == "STRICT_FACTION" and faction_id is None:
        QMessageBox.information(self, "Faction required", "Select a faction before using Strict Faction equipment access."); return
    # STRICT_FACTION filtering re-classifies every scanned weapon's
    # faction affinity against every scanned faction's known_* lists
    # (analysis/equipment_affinity.py) -- on a large real install this
    # is a real, non-instant computation, and unlike every other
    # backend call in this file it runs synchronously on the GUI
    # thread (a modal QInputDialog needs the result immediately
    # afterwards, so it can't go through the background-thread _run()
    # pattern without restructuring this into an async flow). A wait
    # cursor plus a status-bar message is the minimal, low-risk way to
    # signal "working" for that duration.
    self.statusBar().showMessage("Finding backend-eligible weapons for this mount…")
    QApplication.setOverrideCursor(Qt.WaitCursor)
    try:
        eligible = api.run_slot_eligible_weapons(self._registry, self._current_hull.id, slot_id, include_hidden=self.slot_include_hidden.isChecked(), faction_id=str(faction_id) if faction_id else None, faction_mode=faction_mode)
    except ValueError as exc:
        # Reachable when self._current_hull/slot data has gone stale
        # relative to self._registry -- e.g. an incremental dropped-mod
        # incorporation (see _apply_incremental_scan_outcome) made the
        # displayed hull ambiguous after it was selected but before this
        # slot was double-clicked. Previously unguarded: this raised a
        # bare ValueError straight out of a Qt slot instead of the
        # QMessageBox.critical every other backend call in this file
        # routes failures through.
        self._operation_failed(str(exc)); return
    finally:
        QApplication.restoreOverrideCursor()
    choices = ["<Empty>", *[f"{x.name} [{x.id}] — {x.source_mod}" for x in eligible]]; choice, accepted = QInputDialog.getItem(self, "Select legal weapon", slot_id, choices, 0, True)
    if not accepted: return
    mirror_id = self._mirror_pairs.get(slot_id) if self.mirror_fitting.isChecked() else None
    if mirror_id is not None and mirror_id in self._current_hull.built_in_weapons: mirror_id = None
    if choice == "<Empty>":
        self._fit_weapons.pop(slot_id, None)
        if mirror_id is not None: self._fit_weapons.pop(mirror_id, None)
    else:
        selected = next((weapon for weapon in eligible if f"{weapon.name} [{weapon.id}] — {weapon.source_mod}" == choice), None)
        if selected is None: QMessageBox.warning(self, "Invalid selection", "Choose an item from the backend-filtered list."); return
        self._fit_weapons[slot_id] = selected.id
        if mirror_id is not None: self._fit_weapons[mirror_id] = selected.id
    fit = Variant(f"gui_{self._current_hull.id}", "GUI Fit", "GENERATED", self._current_hull.source_path, hull_id=self._current_hull.id, weapons_by_mount=dict(self._fit_weapons)); assessment = api.run_validate_fit(self._registry, fit); details = "; ".join(x.message for x in (*assessment.failures, *assessment.uncertainties))
    self.statusBar().showMessage(f"{assessment.result}: {details or 'No legality findings.'}"); self._update_fit_metrics(); self.canvas.show_hull(self._current_hull, self._fit_weapons, self._registry.weapons.by_id); self.inspect_detail.appendPlainText(f"\nManual fit legality: {assessment.result}\n{details}")


def _generate(self: MainWindow) -> None:
    if self._registry is not None and self._current_hull is not None:
        if self._registry_write_in_progress():
            self.statusBar().showMessage("A scan or mod incorporation is still in progress; wait for it to finish before generating.")
            return
        hull_id = self._current_hull.id
        mode = str(self.mode_selector.currentData())
        profile = self.profile_selector.currentData()
        faction_mode = str(self.faction_mode_selector.currentData())
        faction_id = self.generation_faction_selector.currentData()
        flux_mode = str(self.flux_selector.currentData())
        max_candidates = self.max_candidates.value()
        search_depth = self.search_depth.value()
        config_text = self.advanced_config.text().strip()
        advanced_config = Path(config_text) if config_text else None
        if advanced_config is not None and not advanced_config.is_file():
            QMessageBox.warning(self, "Invalid advanced request", "Choose an existing JSON request file or clear the field.")
            return
        if advanced_config is not None and mode != "advanced":
            QMessageBox.warning(self, "Advanced request", "Select Advanced / Manual mode before applying an advanced request.")
            return
        if faction_mode == "STRICT_FACTION" and faction_id is None:
            QMessageBox.warning(self, "Faction required", "Select a faction before using Strict Faction equipment access.")
            return
        heuristic_set = self._config.heuristic_set if self._config is not None else DEFAULT_HEURISTIC_SET
        self._run(
            "Generating legal build candidates…",
            lambda: api.run_generate(
                self._registry, heuristic_set, hull_id, mode, profile=profile, faction_id=str(faction_id) if faction_id else None,
                faction_mode=faction_mode, advanced_config=advanced_config,
                flux_mode=flux_mode, max_candidates=max_candidates, search_depth=search_depth,
            ),
            self._generation_complete, self.generate_button,
        )


def _generation_complete(self: MainWindow, outcome: Any) -> None:
    text = format_generation_results(outcome.assessed_candidates, outcome.selected_profile, outcome.flux_mode)
    self._generated_candidates = list(outcome.assessed_candidates)
    self.candidate_cards.blockSignals(True); self.candidate_cards.clear()
    for index, candidate in enumerate(self._generated_candidates, 1):
        build = candidate.get("build_archetype", {})
        label = candidate.get("recommendation_label") or build.get("role") or "Candidate"
        score = candidate.get("build_recommendation_score", candidate.get("quality", {}).get("final_score"))
        confidence = build.get("confidence")
        item = QListWidgetItem(f"{index}. {label}\nScore: {score if score is not None else 'Unavailable'}   Confidence: {confidence if confidence is not None else 'Unavailable'}")
        item.setData(Qt.UserRole, index - 1); self.candidate_cards.addItem(item)
    self.candidate_cards.blockSignals(False)
    self.open_advanced_button.setEnabled(bool(self._generated_candidates))
    if self._generated_candidates: self.candidate_cards.setCurrentRow(0)
    else: self.build_results.setPlainText(text)
    self.compare_detail.setPlainText(text); self.statusBar().showMessage("Generation complete.")


def _preview_candidate(self: MainWindow, row: int) -> None:
    if row < 0 or row >= len(self._generated_candidates): return
    candidate = self._generated_candidates[row]
    self.build_results.setPlainText(format_generation_results([candidate], "Selected candidate", "Backend supplied"))
    variant = candidate.get("variant", {})
    weapons = variant.get("weapons_by_mount")
    if self._current_hull is not None and isinstance(weapons, dict):
        self._fit_weapons = {str(mount): str(weapon) for mount, weapon in weapons.items()}
        self.canvas.show_hull(self._current_hull, self._fit_weapons, self._registry.weapons.by_id if self._registry is not None else None)


def _open_selected_in_advanced(self: MainWindow) -> None:
    """Keep the selected backend result visible; never regenerate it here."""
    row = self.candidate_cards.currentRow()
    if row < 0 or row >= len(self._generated_candidates): return
    profile_id = self._generated_candidates[row].get("profile_id")
    if isinstance(profile_id, str):
        index = self.profile_selector.findData(profile_id)
        if index >= 0: self.profile_selector.setCurrentIndex(index)
    mode_index = self.mode_selector.findData("advanced")
    if mode_index >= 0: self.mode_selector.setCurrentIndex(mode_index)
    self.build_results.appendPlainText("Opened in Advanced controls without regenerating; the selected candidate remains on the fitting canvas.")
    self.statusBar().showMessage("Selected candidate preserved in Advanced / Manual controls.")


def _variant_id(self: MainWindow) -> str | None:
    item = self.variant_list.currentItem(); return str(item.data(Qt.UserRole)) if item is not None else None


def _refit(self: MainWindow, operation: Callable[[str], Any], button: QPushButton, message: str, on_result: Callable[[Any], None] | None = None) -> None:
    variant_id = self._variant_id()
    if self._registry is None or variant_id is None: self.refit_detail.setPlainText("Select an existing scanned variant first."); return
    if self._registry_write_in_progress(): self.refit_detail.setPlainText("A scan or mod incorporation is still in progress; wait for it to finish first."); return
    self._run(message, lambda: operation(variant_id), on_result or (lambda result: self.refit_detail.setPlainText(str(result))), button)


def _export_current(self: MainWindow) -> None:
    if self._registry is None or self._current_hull is None: QMessageBox.information(self, "No hull selected", "Select a scanned hull before exporting."); return
    output_text = self.output.text().strip()
    # Mirrors _start_scan's own check on this same field: without it, a
    # cleared output box wouldn't raise or warn at all -- write_variant
    # creates missing parent directories on demand, so Path("") would
    # silently resolve to (and write under) the current working
    # directory instead of anywhere the user chose.
    if not output_text: QMessageBox.warning(self, "Output directory required", "Choose a safe output directory for generated reports and local cache data."); return
    if self._registry_write_in_progress(): self.statusBar().showMessage("A scan or mod incorporation is still in progress; wait for it to finish before exporting."); return
    output, hull_id = Path(output_text), self._current_hull.id
    heuristic_set = self._config.heuristic_set if self._config is not None else DEFAULT_HEURISTIC_SET
    self._run("Creating conservative compatibility-mod export…", lambda: api.run_export(self._registry, heuristic_set, output, hull_id, "LINE_BRAWLER"), lambda path: self.statusBar().showMessage(f"Export complete: {path}"), self.export_button)
