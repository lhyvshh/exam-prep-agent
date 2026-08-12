import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor

from exam_prep.ingestion.pipeline import IngestionPipeline

logger = logging.getLogger(__name__)


class MaterialJobRunner:
    def __init__(self, pipeline: IngestionPipeline) -> None:
        self.pipeline = pipeline
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="material-job")
        self._futures: dict[str, Future[None]] = {}
        self._lock = threading.Lock()

    def enqueue(self, material_id: str) -> None:
        with self._lock:
            existing = self._futures.get(material_id)
            if existing is not None and not existing.done():
                return
            future = self.executor.submit(self._process, material_id)
            self._futures[material_id] = future
            future.add_done_callback(lambda _: self._clear(material_id))

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=False)

    def _clear(self, material_id: str) -> None:
        with self._lock:
            self._futures.pop(material_id, None)

    def _process(self, material_id: str) -> None:
        try:
            self.pipeline.process_registered_material(material_id)
        except Exception:  # noqa: BLE001
            logger.exception("Material processing job failed material_id=%s", material_id)
