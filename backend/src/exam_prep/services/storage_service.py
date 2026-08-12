from pathlib import Path


class StorageService:
    def __init__(self, base_path: Path) -> None:
        self.base_path = base_path

    def ensure_directories(self) -> None:
        self.base_path.mkdir(parents=True, exist_ok=True)
