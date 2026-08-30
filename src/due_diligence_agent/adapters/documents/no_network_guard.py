from __future__ import annotations

from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec, PathFinder
import os
import socket
import sys
from types import ModuleType, TracebackType
from typing import Any, ClassVar
from unittest.mock import patch


class NoNetworkViolation(RuntimeError):
    """Raised before a parser can make a network or model-hub request."""


def _model_hub_violation(*_args: object, **_kwargs: object) -> None:
    raise NoNetworkViolation("network access blocked: model_hub")


class _GuardedHubLoader(Loader):
    def __init__(self, guard: NoNetworkGuard, wrapped: Loader) -> None:
        self._guard = guard
        self._wrapped = wrapped

    def create_module(self, spec: ModuleSpec) -> ModuleType | None:
        create = getattr(self._wrapped, "create_module", None)
        if create is None:
            return None
        return create(spec)  # type: ignore[no-any-return]

    def exec_module(self, module: ModuleType) -> None:
        self._wrapped.exec_module(module)
        self._guard._patch_hub_module(module)


class _HubImportFinder(MetaPathFinder):
    def __init__(self, guard: NoNetworkGuard) -> None:
        self._guard = guard

    def find_spec(
        self,
        fullname: str,
        path: Any = None,
        target: ModuleType | None = None,
    ) -> ModuleSpec | None:
        if not _is_hub_module(fullname):
            return None
        spec = PathFinder.find_spec(fullname, path, target)
        if spec is not None and spec.loader is not None:
            spec.loader = _GuardedHubLoader(self._guard, spec.loader)
        return spec


class NoNetworkGuard:
    _OFFLINE_ENV = {
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
    }
    _HUB_FUNCTIONS = frozenset({"hf_hub_download", "snapshot_download"})
    _ACTIVE_GUARDS: ClassVar[list[NoNetworkGuard]] = []

    def __init__(self) -> None:
        self._patches: list[Any] = []
        self._prior_env: dict[str, str | None] = {}
        self._prior_hub_modules: set[str] = set()
        self._hub_attributes: list[tuple[ModuleType, str, Any]] = []
        self._finder = _HubImportFinder(self)

    def __enter__(self) -> NoNetworkGuard:
        self._prior_env = {name: os.environ.get(name) for name in self._OFFLINE_ENV}
        self._prior_hub_modules = {
            name for name in sys.modules if _is_hub_module(name)
        }
        os.environ.update(self._OFFLINE_ENV)
        self._patches = [
            patch("socket.create_connection", side_effect=self._socket_violation),
            patch.object(socket.socket, "connect", self._blocked_socket_connect),
            patch("urllib.request.urlopen", side_effect=self._socket_violation),
        ]
        try:
            for active_patch in self._patches:
                active_patch.start()
            for name in sorted(self._prior_hub_modules):
                module = sys.modules.get(name)
                if isinstance(module, ModuleType):
                    self._patch_hub_module(module)
            sys.meta_path.insert(0, self._finder)
            self._ACTIVE_GUARDS.append(self)
        except Exception:
            self._restore()
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        self._restore()

    def _patch_hub_module(self, module: ModuleType) -> None:
        for name in self._HUB_FUNCTIONS:
            if hasattr(module, name):
                original = getattr(module, name)
                if original is _model_hub_violation:
                    continue
                self._hub_attributes.append((module, name, original))
                setattr(module, name, _model_hub_violation)

    def _restore(self) -> None:
        outer_guard = next(
            (guard for guard in reversed(self._ACTIVE_GUARDS) if guard is not self),
            None,
        )
        self._ACTIVE_GUARDS[:] = [
            guard for guard in self._ACTIVE_GUARDS if guard is not self
        ]
        while self._finder in sys.meta_path:
            sys.meta_path.remove(self._finder)
        for module, name, original in reversed(self._hub_attributes):
            if outer_guard is None:
                setattr(module, name, original)
            else:
                outer_guard._adopt_hub_attribute(module, name, original)
                setattr(module, name, _model_hub_violation)
        self._hub_attributes.clear()
        if outer_guard is None:
            for name in tuple(sys.modules):
                if _is_hub_module(name) and name not in self._prior_hub_modules:
                    sys.modules.pop(name, None)
        for active_patch in reversed(self._patches):
            active_patch.stop()
        self._patches.clear()
        for name, value in self._prior_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def _adopt_hub_attribute(self, module: ModuleType, name: str, original: Any) -> None:
        if any(
            owned_module is module and owned_name == name
            for owned_module, owned_name, _owned_original in self._hub_attributes
        ):
            return
        self._hub_attributes.append((module, name, original))

    @staticmethod
    def _socket_violation(*_args: object, **_kwargs: object) -> None:
        raise NoNetworkViolation("network access blocked: socket")

    @staticmethod
    def _blocked_socket_connect(
        _socket: socket.socket,
        *_args: object,
        **_kwargs: object,
    ) -> None:
        raise NoNetworkViolation("network access blocked: socket")

def _is_hub_module(name: str) -> bool:
    return name == "huggingface_hub" or name.startswith("huggingface_hub.")
