"""Conservative per-account persistent-profile paths and locks."""

import os
from pathlib import Path
from uuid import UUID

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows unit-test fallback only.
    fcntl = None  # type: ignore[assignment]

from app.instagram.collector.runtime.errors import CollectorRuntimeError, RuntimeReasonCode


def profile_path(profile_root: Path, account_id: UUID) -> Path:
    try:
        root = profile_root.resolve(strict=False)
        candidate = (root / str(account_id)).resolve(strict=False)
    except OSError as error:
        raise CollectorRuntimeError(RuntimeReasonCode.PROFILE_IN_USE) from error
    if root not in candidate.parents:
        raise CollectorRuntimeError(RuntimeReasonCode.PROFILE_IN_USE)
    return candidate


class ProfileLock:
    def __init__(self, profile_directory: Path) -> None:
        self._path = profile_directory / ".collector.lock"
        self._held = False
        self._descriptor: int | None = None

    def acquire(self) -> None:
        if fcntl is not None:
            self._acquire_posix()
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as error:
            raise CollectorRuntimeError(RuntimeReasonCode.PROFILE_IN_USE) from error
        except OSError as error:
            raise CollectorRuntimeError(RuntimeReasonCode.PROFILE_IN_USE) from error
        try:
            os.write(descriptor, b"collector-lock\n")
        except OSError as error:
            try:
                self._path.unlink(missing_ok=True)
            except OSError:
                pass
            raise CollectorRuntimeError(RuntimeReasonCode.PROFILE_IN_USE) from error
        finally:
            os.close(descriptor)
        self._held = True

    def _acquire_posix(self) -> None:
        descriptor: int | None = None
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(self._path, os.O_CREAT | os.O_RDWR, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.ftruncate(descriptor, 0)
            os.write(descriptor, b"offline-reels-profile-lock\n")
        except OSError as error:
            if descriptor is not None:
                os.close(descriptor)
            raise CollectorRuntimeError(RuntimeReasonCode.PROFILE_IN_USE) from error
        self._descriptor = descriptor
        self._held = True

    def release(self) -> None:
        if self._held:
            if self._descriptor is not None and fcntl is not None:
                try:
                    fcntl.flock(self._descriptor, fcntl.LOCK_UN)
                except OSError:
                    pass
                finally:
                    os.close(self._descriptor)
                    self._descriptor = None
                    self._held = False
                return
            try:
                self._path.unlink(missing_ok=True)
            except OSError:
                # Best effort only: never surface a filesystem error while the
                # caller is preserving a prior safe runtime result.
                pass
            self._held = False

    def __enter__(self) -> ProfileLock:
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        del exc_type, exc_value, traceback
        self.release()
