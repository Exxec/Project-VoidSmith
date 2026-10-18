"""Save operations use the existing retained-thread, result-discard lifecycle."""
from .analysis_worker import AnalysisWorker


class SaveWorker(AnalysisWorker):
    """Inspect, plan and (default-off Workshop only) verified-copy write operations; the original save is never modified."""
