from __future__ import annotations

import atexit

from python_qt_binding import QtCore

from fabric_experience_gui.services.fabric_graph_client import FabricGraphClient


_active_requests = set()


@atexit.register
def _wait_for_active_requests():
    for worker in tuple(_active_requests):
        worker.wait()


class _GraphRequest(QtCore.QThread):
    def __init__(self, revision, source, plan_xml, include_dependencies, client_factory):
        super().__init__()
        self.revision = revision
        self.source = source
        self.plan_xml = plan_xml
        self.include_dependencies = include_dependencies
        self.client_factory = client_factory
        self.result = None
        self.error = ''
        self.finished.connect(self._retire)

    @QtCore.Slot()
    def _retire(self):
        _active_requests.discard(self)
        self.deleteLater()

    def run(self):
        client = None
        result = None
        error = ''
        try:
            client = self.client_factory()
            if self.source == 'live':
                result = client.snapshot(include_dependencies=self.include_dependencies)
            elif self.source == 'runnable':
                result = client.runnable_specs()
            else:
                result = client.parse(self.plan_xml)
        except Exception as exc:
            error = str(exc) or type(exc).__name__
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception as exc:
                    if not error:
                        error = str(exc) or type(exc).__name__
        self.result = result
        self.error = error


class FabricGraphRequests(QtCore.QObject):
    capture_ready = QtCore.Signal(object)
    failed = QtCore.Signal(str)
    busy_changed = QtCore.Signal(bool)

    def __init__(self, parent=None, *, client_factory=FabricGraphClient):
        super().__init__(parent)
        self._client_factory = client_factory
        self._revision = 0
        self._worker = None
        self._pending = None
        self._closed = False

    def request(self, source: str, plan_xml: str = '', *, include_dependencies: bool = False):
        if source not in ('live', 'loaded', 'runnable'):
            raise ValueError('source must be live, loaded, or runnable')
        if self._closed:
            return
        self._revision += 1
        self._pending = (self._revision, source, plan_xml, include_dependencies)
        if self._worker is None:
            self._start_pending()

    def invalidate(self):
        self._revision += 1
        self._pending = None

    def close(self):
        self._closed = True
        self.invalidate()

    def _start_pending(self):
        if self._closed or self._pending is None:
            return
        revision, source, plan_xml, include_dependencies = self._pending
        self._pending = None
        self._worker = _GraphRequest(revision, source, plan_xml, include_dependencies, self._client_factory)
        self._worker.finished.connect(self._on_completed)
        _active_requests.add(self._worker)
        self.busy_changed.emit(True)
        self._worker.start()

    @QtCore.Slot()
    def _on_completed(self):
        worker = self.sender()
        revision, result, error = worker.revision, worker.result, worker.error
        self._worker = None
        if not self._closed and revision == self._revision:
            if error:
                self.failed.emit(error)
            else:
                self.capture_ready.emit(result)
        if not self._closed and self._pending is not None:
            self._start_pending()
        else:
            self.busy_changed.emit(False)