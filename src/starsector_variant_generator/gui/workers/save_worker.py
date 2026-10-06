"""Save operations use the existing retained-thread, result-discard lifecycle."""
from .analysis_worker import AnalysisWorker


class SaveWorker(AnalysisWorker):
    """Read-only inspect and plan operations; no write operation exists yet."""
