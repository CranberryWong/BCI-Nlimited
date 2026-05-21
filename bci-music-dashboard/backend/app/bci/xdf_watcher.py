from __future__ import annotations

from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from app.bci.model_runner import ModelRunner


class _XdfHandler(FileSystemEventHandler):
    def __init__(self, runner: ModelRunner) -> None:
        self.runner = runner

    def on_created(self, event) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() != ".xdf" or "amplifier" not in path.parts:
            return
        self.runner.process_xdf(path)


class XdfWatcher:
    def __init__(self, root_dir: Path, runner: ModelRunner) -> None:
        self.root_dir = root_dir
        self.runner = runner
        self.observer: Observer | None = None

    @property
    def running(self) -> bool:
        return bool(self.observer and self.observer.is_alive())

    def start(self) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        if self.running:
            return
        self.observer = Observer()
        self.observer.schedule(_XdfHandler(self.runner), str(self.root_dir), recursive=True)
        self.observer.start()

    def stop(self) -> None:
        if not self.observer:
            return
        self.observer.stop()
        self.observer.join(timeout=3)
        self.observer = None
        self.runner.reset()
