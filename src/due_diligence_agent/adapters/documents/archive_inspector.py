from __future__ import annotations

import codecs
from collections.abc import Iterator
import csv
from dataclasses import dataclass
from hashlib import sha256
from io import StringIO
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
from shutil import rmtree
import stat
from typing import IO, Final
from uuid import uuid4
import zipfile
import zlib

from due_diligence_agent.domain.artifacts.models import SourceLocator
from due_diligence_agent.domain.artifacts.safety import (
    SafetyLimits,
    SafetyScanResult,
    ScannedArtifact,
)

_PDF = "application/pdf"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_CSV = "text/csv"
_PLAIN_TEXT = "text/plain"
_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PNG = "image/png"
_JPEG = "image/jpeg"
_ZIP = "application/zip"

_EXPECTED_BY_SUFFIX: Final[dict[str, str]] = {
    ".pdf": _PDF,
    ".xlsx": _XLSX,
    ".csv": _CSV,
    ".txt": _PLAIN_TEXT,
    ".docx": _DOCX,
    ".png": _PNG,
    ".jpg": _JPEG,
    ".jpeg": _JPEG,
    ".zip": _ZIP,
}
_SUPPORTED_COMPRESSIONS: Final[frozenset[int]] = frozenset(
    {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
)
_CHUNK_BYTES: Final[int] = 1024 * 1024
_SNIFF_BYTES: Final[int] = 64 * 1024


class UnsafeArchiveError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class _Budget:
    max_files: int
    max_unpacked_bytes: int
    files: int = 0
    unpacked_bytes: int = 0

    def reserve(self, byte_size: int) -> None:
        if self.files + 1 > self.max_files:
            raise UnsafeArchiveError("file_count_exceeded")
        if self.unpacked_bytes + byte_size > self.max_unpacked_bytes:
            raise UnsafeArchiveError("unpacked_size_exceeded")
        self.files += 1
        self.unpacked_bytes += byte_size

    def reserve_unpacked_bytes(self, byte_size: int) -> None:
        if self.unpacked_bytes + byte_size > self.max_unpacked_bytes:
            raise UnsafeArchiveError("unpacked_size_exceeded")
        self.unpacked_bytes += byte_size


class ZipArchiveInspector:
    def __init__(
        self,
        *,
        limits: SafetyLimits | None = None,
        staging_root: Path | None = None,
    ) -> None:
        self.limits = limits or SafetyLimits()
        self._staging_root = staging_root.resolve() if staging_root is not None else None

    def inspect(
        self,
        source: Path,
        *,
        remaining_files: int,
        remaining_unpacked_bytes: int,
    ) -> SafetyScanResult:
        resolved_source = source.resolve(strict=True)
        locator = SourceLocator(kind="file", value=str(resolved_source))
        byte_size = resolved_source.stat().st_size
        if byte_size > self.limits.max_file_bytes:
            return self._rejected(locator, self._hash_path(resolved_source), "file_size_exceeded")
        digest = self._hash_path(resolved_source)
        transaction_root = self._create_transaction_root()
        budget = _Budget(
            max_files=max(0, remaining_files),
            max_unpacked_bytes=max(0, remaining_unpacked_bytes),
        )
        try:
            media_type = self._media_type_path(
                resolved_source,
                source.name,
                allow_plain_text=True,
            )
            media_type = self._validate_media_type(media_type, source.name)
            if media_type == _ZIP:
                if self.limits.max_archive_depth < 1:
                    raise UnsafeArchiveError("archive_depth_exceeded")
                accepted = self._inspect_archive_path(
                    resolved_source,
                    display_name=source.name,
                    depth=1,
                    transaction_root=transaction_root,
                    budget=budget,
                )
            else:
                accounted_size = byte_size
                if media_type in {_DOCX, _XLSX}:
                    accounted_size = self._preflight_office_path(resolved_source)
                budget.reserve(accounted_size)
                accepted = (
                    self._stage_path(
                        resolved_source,
                        source=SourceLocator(kind="file", value=source.name),
                        media_type=media_type,
                        transaction_root=transaction_root,
                    ),
                )
        except (UnsafeArchiveError, zipfile.BadZipFile, EOFError, RuntimeError, OSError) as exc:
            rmtree(transaction_root, ignore_errors=True)
            reason = exc.reason if isinstance(exc, UnsafeArchiveError) else "damaged_archive"
            return self._rejected(locator, digest, reason)
        return SafetyScanResult(
            source=locator,
            source_content_hash=digest,
            accepted=accepted,
            file_count=budget.files,
            accounted_unpacked_bytes=budget.unpacked_bytes,
            unpacked_bytes=sum(item.byte_size for item in accepted),
        ).attach_transaction(transaction_root)

    def _inspect_archive_path(
        self,
        archive_path: Path,
        *,
        display_name: str,
        depth: int,
        transaction_root: Path,
        budget: _Budget,
    ) -> tuple[ScannedArtifact, ...]:
        with zipfile.ZipFile(archive_path) as archive:
            infos = self._preflight_archive(archive, budget)
            accepted: list[ScannedArtifact] = []
            for info in infos:
                staged_member = self._stage_member(
                    archive,
                    info,
                    transaction_root=transaction_root,
                )
                media_type = self._media_type_path(
                    staged_member,
                    info.filename,
                    allow_plain_text=True,
                )
                media_type = self._validate_media_type(media_type, info.filename)
                member_name = f"{display_name}!/{self._canonical_member_path(info.filename)}"
                if media_type == _ZIP:
                    if depth >= self.limits.max_archive_depth:
                        raise UnsafeArchiveError("archive_depth_exceeded")
                    accepted.extend(
                        self._inspect_archive_path(
                            staged_member,
                            display_name=member_name,
                            depth=depth + 1,
                            transaction_root=transaction_root,
                            budget=budget,
                        )
                    )
                    staged_member.unlink(missing_ok=True)
                    continue
                if media_type in {_DOCX, _XLSX}:
                    budget.reserve_unpacked_bytes(self._preflight_office_path(staged_member))
                accepted.append(
                    self._scanned_from_staged(
                        staged_member,
                        source=SourceLocator(kind="archive_member", value=member_name),
                        media_type=media_type,
                    )
                )
            return tuple(accepted)

    def _preflight_archive(
        self,
        archive: zipfile.ZipFile,
        budget: _Budget,
    ) -> list[zipfile.ZipInfo]:
        all_infos = archive.infolist()
        self._validate_member_set(all_infos)
        infos = [info for info in all_infos if not info.is_dir()]
        if not infos:
            raise UnsafeArchiveError("damaged_archive")
        total_unpacked = 0
        total_compressed = 0
        for info in infos:
            self._validate_member_metadata(info)
            budget.reserve(info.file_size)
            total_unpacked += info.file_size
            total_compressed += info.compress_size
        if total_unpacked / max(total_compressed, 1) > self.limits.max_decompression_ratio:
            raise UnsafeArchiveError("decompression_ratio_exceeded")
        return infos

    def _preflight_office_path(self, path: Path) -> int:
        with zipfile.ZipFile(path) as archive:
            all_infos = archive.infolist()
            self._validate_member_set(all_infos)
            infos = [info for info in all_infos if not info.is_dir()]
            total_unpacked = 0
            total_compressed = 0
            for info in infos:
                self._validate_member_metadata(info)
                total_unpacked += info.file_size
                total_compressed += info.compress_size
            if total_unpacked > self.limits.max_unpacked_bytes:
                raise UnsafeArchiveError("unpacked_size_exceeded")
            if total_unpacked / max(total_compressed, 1) > self.limits.max_decompression_ratio:
                raise UnsafeArchiveError("decompression_ratio_exceeded")
            return total_unpacked

    def _validate_member_metadata(self, info: zipfile.ZipInfo) -> None:
        if info.flag_bits & 0x1:
            raise UnsafeArchiveError("unsupported_archive_member")
        mode = (info.external_attr >> 16) & 0xFFFF
        if stat.S_ISLNK(mode):
            raise UnsafeArchiveError("unsupported_archive_member")
        if info.compress_type not in _SUPPORTED_COMPRESSIONS:
            raise UnsafeArchiveError("unsupported_compression")
        if info.file_size > self.limits.max_file_bytes:
            raise UnsafeArchiveError("file_size_exceeded")
        if info.file_size / max(info.compress_size, 1) > self.limits.max_decompression_ratio:
            raise UnsafeArchiveError("decompression_ratio_exceeded")

    def _validate_member_set(self, infos: list[zipfile.ZipInfo]) -> None:
        exact_paths: set[str] = set()
        folded_paths: dict[str, str] = {}
        for info in infos:
            canonical = self._canonical_member_path(info.filename)
            if canonical in exact_paths:
                raise UnsafeArchiveError("duplicate_archive_path")
            folded = canonical.casefold()
            prior = folded_paths.get(folded)
            if prior is not None:
                raise UnsafeArchiveError("archive_path_case_collision")
            exact_paths.add(canonical)
            folded_paths[folded] = canonical

    def _stage_member(
        self,
        archive: zipfile.ZipFile,
        info: zipfile.ZipInfo,
        *,
        transaction_root: Path,
    ) -> Path:
        target = transaction_root / f"{uuid4().hex}.stage"
        try:
            with archive.open(info, "r") as member:
                self._stream_to_path(member, target, limit=info.file_size)
        except (NotImplementedError, zipfile.BadZipFile, EOFError, RuntimeError, zlib.error) as exc:
            target.unlink(missing_ok=True)
            raise UnsafeArchiveError("archive_decompression_failed") from exc
        return target

    def _stage_path(
        self,
        source_path: Path,
        *,
        source: SourceLocator,
        media_type: str,
        transaction_root: Path,
    ) -> ScannedArtifact:
        target = transaction_root / f"{uuid4().hex}.stage"
        with source_path.open("rb") as input_file:
            self._stream_to_path(input_file, target, limit=source_path.stat().st_size)
        return self._scanned_from_staged(target, source=source, media_type=media_type)

    def _stream_to_path(self, stream: IO[bytes], target: Path, *, limit: int) -> None:
        total = 0
        try:
            with target.open("xb") as output:
                for chunk in self._bounded_chunks(stream, limit=limit):
                    output.write(chunk)
                    total += len(chunk)
                output.flush()
                os.fsync(output.fileno())
        except Exception:
            target.unlink(missing_ok=True)
            raise
        if total != limit:
            target.unlink(missing_ok=True)
            raise UnsafeArchiveError("archive_decompression_failed")

    @staticmethod
    def _bounded_chunks(stream: IO[bytes], *, limit: int) -> Iterator[bytes]:
        total = 0
        while total < limit:
            chunk = stream.read(min(_CHUNK_BYTES, limit - total))
            if not chunk:
                break
            total += len(chunk)
            yield chunk
        if stream.read(1):
            raise UnsafeArchiveError("file_size_exceeded")

    def _media_type_path(
        self,
        path: Path,
        filename: str,
        *,
        allow_plain_text: bool = False,
    ) -> str | None:
        with path.open("rb") as file:
            header = file.read(_SNIFF_BYTES)
        if header.startswith(b"%PDF-"):
            return _PDF
        if header.startswith(b"\x89PNG\r\n\x1a\n"):
            return _PNG
        if header.startswith(b"\xff\xd8\xff"):
            return _JPEG
        if header.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
            try:
                with zipfile.ZipFile(path) as archive:
                    names = set(archive.namelist())
            except (zipfile.BadZipFile, EOFError):
                if Path(filename).suffix.lower() == ".zip":
                    raise UnsafeArchiveError("damaged_archive")
                return None
            if "[Content_Types].xml" in names and "word/document.xml" in names:
                return _DOCX
            if "[Content_Types].xml" in names and "xl/workbook.xml" in names:
                return _XLSX
            return _ZIP
        if self._is_csv_path(path):
            return _CSV
        if (
            allow_plain_text
            and Path(filename).suffix.casefold() == ".txt"
            and self._is_safe_plain_text_path(path)
        ):
            return _PLAIN_TEXT
        return None

    @staticmethod
    def _is_csv_path(path: Path) -> bool:
        with path.open("rb") as file:
            payload = file.read(_SNIFF_BYTES)
        if not payload or b"\x00" in payload:
            return False
        try:
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError:
            return False
        if any(ord(char) < 32 and char not in "\r\n\t" for char in text):
            return False
        try:
            dialect = csv.Sniffer().sniff(text, delimiters=",;\t")
            rows = list(csv.reader(StringIO(text), dialect))
        except csv.Error:
            return False
        nonempty = [row for row in rows if row]
        if not nonempty or len(nonempty[0]) < 2:
            return False
        width = len(nonempty[0])
        return all(len(row) == width for row in nonempty[:100])

    @staticmethod
    def _is_safe_plain_text_path(path: Path) -> bool:
        decoder = codecs.getincrementaldecoder("utf-8-sig")("strict")
        has_non_whitespace = False
        try:
            with path.open("rb") as file:
                while chunk := file.read(_CHUNK_BYTES):
                    if b"\x00" in chunk:
                        return False
                    text = decoder.decode(chunk)
                    if any(ord(char) < 32 and char not in "\r\n\t" for char in text):
                        return False
                    has_non_whitespace = has_non_whitespace or any(
                        not char.isspace() for char in text
                    )
            tail = decoder.decode(b"", final=True)
        except UnicodeDecodeError:
            return False
        if any(ord(char) < 32 and char not in "\r\n\t" for char in tail):
            return False
        return has_non_whitespace or any(not char.isspace() for char in tail)

    def _validate_media_type(self, media_type: str | None, filename: str) -> str:
        expected = _EXPECTED_BY_SUFFIX.get(Path(filename).suffix.lower())
        if media_type is None:
            reason = "damaged_archive" if expected == _ZIP else "unsupported_media_type"
            raise UnsafeArchiveError(reason)
        if expected is not None and expected != media_type:
            raise UnsafeArchiveError("mime_type_mismatch")
        if media_type not in self.limits.allowed_media_types:
            raise UnsafeArchiveError("unsupported_media_type")
        return media_type

    @staticmethod
    def _scanned_from_staged(
        staged_path: Path,
        *,
        source: SourceLocator,
        media_type: str,
    ) -> ScannedArtifact:
        return ScannedArtifact(
            source=source,
            media_type=media_type,
            content_hash=ZipArchiveInspector._hash_path(staged_path),
            byte_size=staged_path.stat().st_size,
            staged_path=staged_path,
        )

    @staticmethod
    def _canonical_member_path(name: str) -> str:
        if not name or "\x00" in name:
            raise UnsafeArchiveError("zip_slip")
        windows_path = PureWindowsPath(name)
        normalized = name.replace("\\", "/")
        posix_path = PurePosixPath(normalized)
        if (
            name.startswith(("/", "\\"))
            or windows_path.drive
            or windows_path.is_absolute()
            or posix_path.is_absolute()
            or ".." in posix_path.parts
        ):
            raise UnsafeArchiveError("zip_slip")
        canonical = "/".join(part for part in posix_path.parts if part not in {"", "."})
        if not canonical:
            raise UnsafeArchiveError("zip_slip")
        return canonical

    def _create_transaction_root(self) -> Path:
        parent = self._staging_root
        if parent is None:
            from tempfile import gettempdir

            parent = Path(gettempdir()).resolve()
        else:
            parent.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            from tempfile import mkdtemp

            return Path(mkdtemp(prefix="dd-ingest-", dir=str(parent))).resolve()
        return self._create_windows_transaction_root(parent)

    @staticmethod
    def _create_windows_transaction_root(parent: Path) -> Path:
        parent = parent.resolve()
        for _ in range(100):
            candidate = parent / f"dd-ingest-{uuid4().hex}"
            try:
                candidate.mkdir()
            except FileExistsError:
                continue
            return candidate.resolve()
        raise FileExistsError(f"could not allocate staging directory under {parent}")

    @staticmethod
    def _hash_path(source: Path) -> str:
        digest = sha256()
        with source.open("rb") as file:
            for chunk in iter(lambda: file.read(_CHUNK_BYTES), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _rejected(locator: SourceLocator, digest: str, reason: str) -> SafetyScanResult:
        return SafetyScanResult(
            source=locator,
            source_content_hash=digest,
            reason=reason,
        )
