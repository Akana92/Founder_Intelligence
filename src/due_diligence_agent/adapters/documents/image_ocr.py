from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from importlib import import_module
from io import BytesIO
from shutil import which
import subprocess
from typing import Any
import warnings

from PIL import Image, UnidentifiedImageError

from due_diligence_agent.domain.artifacts.models import Artifact, SourceLocator
from due_diligence_agent.domain.documents.models import (
    ParsedDocument,
    ParsedPage,
    ParserStatus,
    TextBlock,
)
from due_diligence_agent.ports.repositories import ArtifactStore


@dataclass(frozen=True)
class ImageSafetyLimits:
    max_width: int = 20_000
    max_height: int = 20_000
    max_pixels: int = 40_000_000

    def __post_init__(self) -> None:
        if self.max_width < 1 or self.max_height < 1 or self.max_pixels < 1:
            raise ValueError("image safety limits must be positive")


@dataclass(frozen=True)
class OcrRegion:
    text: str = field(repr=False)
    confidence: Decimal
    bbox: tuple[int, int, int, int]


@dataclass(frozen=True)
class _OcrCapability:
    module: Any | None = field(default=None, repr=False)
    error_code: str | None = None


class ImageValidationError(ValueError):
    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


class _OcrUnavailable(RuntimeError):
    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


class TesseractOcrAdapter:
    parser_name = "tesseract"
    parser_version = "1"

    def __init__(
        self,
        *,
        recognizer: Callable[[Image.Image], list[OcrRegion]] | None = None,
        binary_probe: Callable[[], str | None] = lambda: which("tesseract"),
        version_runner: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
        module_loader: Callable[[str], Any] = import_module,
        image_limits: ImageSafetyLimits | None = None,
    ) -> None:
        self._recognizer = recognizer
        self._binary_probe = binary_probe
        self._version_runner = version_runner or _run_version
        self._module_loader = module_loader
        self._image_limits = image_limits or ImageSafetyLimits()
        self._capability_cache: _OcrCapability | None = None
        self._artifact_store: ArtifactStore | None = None

    @property
    def image_limits(self) -> ImageSafetyLimits:
        return self._image_limits

    def bind(self, artifact_store: ArtifactStore) -> TesseractOcrAdapter:
        self._artifact_store = artifact_store
        return self

    def parse(self, artifact: Artifact, payload: bytes, *, media_type: str) -> ParsedDocument:
        try:
            image = load_normalized_image(payload, self._image_limits)
        except ImageValidationError as exc:
            return self._outcome(artifact, media_type, "damaged", exc.error_code)

        if self._recognizer is not None:
            try:
                regions = self._recognizer(image)
            except Exception:
                return self._outcome(
                    artifact, media_type, "parser_unavailable", "ocr_runtime_failed"
                )
        else:
            capability = self._local_capability()
            if capability.error_code is not None:
                return self._outcome(
                    artifact, media_type, "parser_unavailable", capability.error_code
                )
            try:
                regions = self._recognize_with_tesseract(image, capability.module)
            except _OcrUnavailable as exc:
                return self._outcome(artifact, media_type, "parser_unavailable", exc.error_code)

        store = self._require_store()
        blocks: list[TextBlock] = []
        for region in regions:
            text = " ".join(region.text.split())
            if not text:
                continue
            stored = store.put_bytes(
                text.encode("utf-8"),
                media_type="text/plain; charset=utf-8",
                artifact_id=artifact.id,
                source_snapshot_hash=artifact.content_hash,
                sensitivity=artifact.sensitivity,
            )
            bbox = ",".join(str(value) for value in region.bbox)
            blocks.append(
                TextBlock(
                    text_ref=stored.content_hash,
                    content_hash=stored.content_hash,
                    char_count=len(text),
                    locator=SourceLocator(
                        kind="image_region",
                        value=f"page:1:bbox:{bbox}",
                        artifact_id=artifact.id,
                        page=1,
                    ),
                    confidence=region.confidence,
                    verification_status=(
                        "needs_review" if region.confidence < Decimal("0.80") else "candidate"
                    ),
                )
            )
        confidence = min((block.confidence for block in blocks), default=Decimal("0"))
        return ParsedDocument(
            artifact_id=artifact.id,
            detected_mime_type=media_type,
            pages=[
                ParsedPage(
                    page_number=1,
                    locator=SourceLocator(
                        kind="image_page",
                        value="page:1",
                        artifact_id=artifact.id,
                        page=1,
                    ),
                    text_blocks=blocks,
                    width=Decimal(image.width),
                    height=Decimal(image.height),
                )
            ],
            text_blocks=blocks,
            parser_name=self.parser_name,
            parser_version=self.parser_version,
            confidence=confidence,
            status="parsed" if blocks else "partial",
            error_code=None if blocks else "no_extractable_content",
        )

    def _local_capability(self) -> _OcrCapability:
        if self._capability_cache is not None:
            return self._capability_cache
        try:
            binary = self._binary_probe()
        except Exception:
            binary = ""
        if not binary:
            self._capability_cache = _OcrCapability(error_code="ocr_binary_missing")
            return self._capability_cache
        try:
            result = self._version_runner([binary, "--version"])
        except (OSError, subprocess.SubprocessError):
            result = None
        version_text = "" if result is None else f"{result.stdout}\n{result.stderr}".lower()
        if result is None or result.returncode != 0 or "tesseract" not in version_text:
            self._capability_cache = _OcrCapability(error_code="ocr_binary_smoke_failed")
            return self._capability_cache
        try:
            module: Any = self._module_loader("pytesseract")
        except ImportError:
            self._capability_cache = _OcrCapability(error_code="ocr_python_adapter_missing")
            return self._capability_cache
        except Exception:
            self._capability_cache = _OcrCapability(error_code="ocr_python_adapter_unusable")
            return self._capability_cache
        output = getattr(module, "Output", None)
        if (
            not callable(getattr(module, "image_to_data", None))
            or output is None
            or not hasattr(output, "DICT")
            or not isinstance(getattr(module, "TesseractError", None), type)
        ):
            self._capability_cache = _OcrCapability(error_code="ocr_python_adapter_unusable")
            return self._capability_cache
        self._capability_cache = _OcrCapability(module=module)
        return self._capability_cache

    @staticmethod
    def _recognize_with_tesseract(image: Image.Image, module: Any) -> list[OcrRegion]:
        try:
            data: Any = module.image_to_data(image, output_type=module.Output.DICT)
        except Exception as exc:
            tesseract_error: type[BaseException] = module.TesseractError
            if isinstance(exc, tesseract_error):
                raise _OcrUnavailable("ocr_tesseract_error") from None
            raise _OcrUnavailable("ocr_runtime_failed") from None
        try:
            if not isinstance(data, dict):
                raise ValueError("invalid OCR mapping")
            names = ("text", "conf", "left", "top", "width", "height")
            columns = {name: data[name] for name in names}
            if any(not isinstance(values, (list, tuple)) for values in columns.values()):
                raise ValueError("invalid OCR column")
            row_count = len(columns["text"])
            if any(len(values) != row_count for values in columns.values()):
                raise ValueError("inconsistent OCR columns")
            regions: list[OcrRegion] = []
            for index, raw_text in enumerate(columns["text"]):
                confidence = _confidence(columns["conf"][index])
                if confidence < 0:
                    continue
                if confidence > 100:
                    raise ValueError("invalid OCR confidence")
                left = int(columns["left"][index])
                top = int(columns["top"][index])
                width = int(columns["width"][index])
                height = int(columns["height"][index])
                if min(left, top, width, height) < 0:
                    raise ValueError("invalid OCR geometry")
                regions.append(
                    OcrRegion(
                        text=str(raw_text),
                        confidence=confidence / Decimal("100"),
                        bbox=(left, top, left + width, top + height),
                    )
                )
            return regions
        except (InvalidOperation, KeyError, TypeError, ValueError):
            raise _OcrUnavailable("ocr_malformed_output") from None

    def _outcome(
        self,
        artifact: Artifact,
        media_type: str,
        status: ParserStatus,
        error_code: str,
    ) -> ParsedDocument:
        return ParsedDocument.outcome(
            artifact_id=artifact.id,
            detected_mime_type=media_type,
            parser_name=self.parser_name,
            parser_version=self.parser_version,
            status=status,
            error_code=error_code,
        )

    def _require_store(self) -> ArtifactStore:
        if self._artifact_store is None:
            raise RuntimeError("artifact store is not bound")
        return self._artifact_store


def detect_image_media_type(payload: bytes, limits: ImageSafetyLimits) -> str | None:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(payload)) as image:
                _check_dimensions(image.width, image.height, limits)
                image_format = image.format
                media_type = (
                    None
                    if image_format is None
                    else {"PNG": "image/png", "JPEG": "image/jpeg"}.get(image_format)
                )
                image.verify()
                return media_type
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ImageValidationError("image_decompression_bomb") from None
    except ImageValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        return None


def load_normalized_image(payload: bytes, limits: ImageSafetyLimits) -> Image.Image:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(payload)) as source:
                _check_dimensions(source.width, source.height, limits)
                normalized = source.convert("RGB")
                normalized.load()
                return normalized
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ImageValidationError("image_decompression_bomb") from None
    except ImageValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise ImageValidationError("damaged_image") from None


def _check_dimensions(width: int, height: int, limits: ImageSafetyLimits) -> None:
    if width > limits.max_width or height > limits.max_height:
        raise ImageValidationError("image_dimensions_exceeded")
    if width * height > limits.max_pixels:
        raise ImageValidationError("image_pixel_limit_exceeded")


def _run_version(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        check=False,
        text=True,
        timeout=5,
    )


def _confidence(value: Any) -> Decimal:
    return Decimal(str(value))
