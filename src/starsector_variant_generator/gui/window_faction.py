"""Window faction helpers for MainWindow; GUI rules stay in the backend."""
from __future__ import annotations

from typing import TYPE_CHECKING
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QInputDialog, QPushButton
from starsector_variant_generator import api
from starsector_variant_generator.analysis.recommendation_feedback import FeedbackKind, RecommendationFeedback
from starsector_variant_generator.core.config import DEFAULT_HEURISTIC_SET
from starsector_variant_generator.gui.presentation import format_build_why_not_comparison

if TYPE_CHECKING:
    from .main_window import MainWindow


def _faction_selected(self: MainWindow, _: int) -> None: self.faction_detail.setPlainText("Choose capability analysis or gap recommendations.") if self._faction_id() else None


def _choose_knowledge_pack(self: MainWindow) -> None:
    path, _ = QFileDialog.getOpenFileName(self, "Choose faction knowledge pack", self.knowledge_pack_path.text(), "JSON files (*.json)")
    if path:
        self.knowledge_pack_path.setText(path)
        self._preferences.setValue("paths/knowledge_pack", path)


def _faction_id(self: MainWindow) -> tuple[str, str | None] | None:
    item = self.faction_list.currentItem(); value = item.data(Qt.UserRole) if item is not None else None; return tuple(value) if isinstance(value, tuple) and len(value) == 2 else None


def _faction_run(self: MainWindow, operation: Callable[[str, str | None], Any], button: QPushButton, message: str) -> None:
    selected = self._faction_id()
    if self._registry is None or selected is None: self.faction_detail.setPlainText("Select a scanned faction first."); return
    if self._registry_write_in_progress(): self.faction_detail.setPlainText("A scan or mod incorporation is still in progress; wait for it to finish first."); return
    faction_id, source_mod = selected; self._run(message, lambda: operation(faction_id, source_mod), lambda result: self.faction_detail.setPlainText(str(result)), button)


def _analyze_capability(self: MainWindow) -> None:
    heuristic_set = self._config.heuristic_set if self._config is not None else DEFAULT_HEURISTIC_SET
    pack_path = self.knowledge_pack_path.text().strip()
    def analyze(faction: str, source: str | None) -> dict[str, object]:
        result: dict[str, object] = {"automatic_capability": api.run_faction_capability(self._registry, faction, source, heuristic_set)}
        if pack_path:
            pack = api.resolve_optional_knowledge_pack(Path(pack_path), self._registry)
            result["knowledge_pack"] = pack
        return result
    self._faction_run(analyze, self.capability_button, "Computing faction capability vector…")


def _gap_recommendations(self: MainWindow) -> None:
    heuristic_set = self._config.heuristic_set if self._config is not None else DEFAULT_HEURISTIC_SET
    pack_path = self.knowledge_pack_path.text().strip()
    def recommend(faction: str, source: str | None) -> object:
        pack = api.resolve_optional_knowledge_pack(Path(pack_path), self._registry) if pack_path else None
        return api.run_gap_recommendations(self._registry, faction, source, heuristic_set, pack)
    self._faction_run(recommend, self.recommend_button, "Ranking Hull + BuildArchetype gap solutions…")


def _compare_build_paths(self: MainWindow) -> None:
    selected = self._faction_id()
    if self._registry is None or selected is None:
        self.faction_detail.setPlainText("Select a scanned faction before comparing build paths."); return
    role = self.build_comparison_role.text().strip().upper()
    entries = [item.strip() for item in self.build_comparison_paths.text().split(",") if item.strip()]
    paths: list[tuple[str, str]] = []
    try:
        for entry in entries:
            hull_id, build_id = (part.strip() for part in entry.split(":", 1))
            if not hull_id or not build_id:
                raise ValueError
            paths.append((hull_id, build_id.upper()))
    except ValueError:
        self.faction_detail.setPlainText("Use comma-separated hull_id:build_id entries, with at least two paths."); return
    if len(paths) < 2 or not role:
        self.faction_detail.setPlainText("Enter one role and at least two build paths."); return
    faction_id, source_mod = selected
    heuristic_set = self._config.heuristic_set if self._config is not None else DEFAULT_HEURISTIC_SET
    self._run("Comparing already-computed Build Why-Not evidence…", lambda: api.run_build_why_not_comparison(self._registry, faction_id, role, tuple(paths), source_mod, heuristic_set), lambda result: self.faction_detail.setPlainText(format_build_why_not_comparison(result)), self.build_comparison_button)


def _save_recommendation_feedback(self: MainWindow) -> None:
    if self._registry is None:
        self.faction_detail.setPlainText("Scan local data before recording feedback."); return
    output_text = self.output.text().strip()
    candidate = self.fleet_support_candidate.text().strip()
    if not output_text or not candidate:
        self.faction_detail.setPlainText("Choose an advisor candidate and configured output directory before recording feedback."); return
    hull = self._registry.hulls.by_id.get(candidate)
    if hull is None:
        self.faction_detail.setPlainText("The selected advisor candidate is no longer a uniquely resolved hull."); return
    kind = FeedbackKind(str(self.feedback_kind.currentData()))
    note, accepted = QInputDialog.getText(self, "Local recommendation feedback", "Optional note (stored locally only):")
    if not accepted:
        return
    try:
        path = api.save_recommendation_feedback(Path(output_text), RecommendationFeedback(kind, f"fleet-support:{candidate}", candidate, hull.source_mod, note or None))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        self.faction_detail.setPlainText(f"Feedback was not saved: {exc}"); return
    self.faction_detail.setPlainText(f"Recorded local {kind.value} feedback for {candidate}.\n{path}\n\nFeedback is review material only; it did not alter legality, recommendation score, confidence, or heuristics.")
