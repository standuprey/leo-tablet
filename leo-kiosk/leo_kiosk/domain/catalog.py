"""Immutable catalog values; source evidence is not proof of playable content."""

import ipaddress
import re
import unicodedata
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from urllib.parse import urlsplit
from uuid import UUID, uuid5

from .errors import ValidationError

# Persisted identity contract: never replace this namespace after catalog import.
CATALOG_NAMESPACE = UUID("d0c20596-e64c-54d7-b3a0-a808cd66c9b8")
_PROVIDER = re.compile(r"[a-z][a-z0-9-]*")
_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


class MediaType(IntEnum):
    OTHER = 0
    VIDEO = 1
    GAME = 2


class Orientation(StrEnum):
    UNKNOWN = "unknown"
    LANDSCAPE = "landscape"
    PORTRAIT = "portrait"
    SQUARE = "square"


class DimensionEvidence(StrEnum):
    UNKNOWN = "unknown"
    DESIGN = "design"
    IFRAME = "iframe"
    POPUP = "popup"
    INFERRED = "inferred"


def validate_provider_id(value: str) -> str:
    if not isinstance(value, str) or not _PROVIDER.fullmatch(value):
        raise ValidationError("Provider ID must be a lowercase stable slug")
    return value


def canonicalize_url(value: str) -> str:
    """Normalize authority only; preserve path, query, fragment and empty delimiters."""
    if not isinstance(value, str) or not value:
        raise ValidationError("A nonempty HTTP(S) URL is required")
    if "\\" in value or any(c.isspace() or unicodedata.category(c)[0] == "C" for c in value):
        raise ValidationError("URL cannot contain whitespace, controls or backslashes")
    try:
        parsed = urlsplit(value)
        scheme = parsed.scheme.lower()
        if scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError
        if parsed.username is not None or parsed.password is not None:
            raise ValueError
        host = parsed.hostname
        port = parsed.port  # Also validates port syntax and range.
        if not host or port == 0 or parsed.netloc.endswith(":"):
            raise ValueError
        if ":" in host:
            if not re.fullmatch(r"\[[^\]]+\](?::[0-9]+)?", parsed.netloc):
                raise ValueError
            if "%" in host:
                raise ValueError  # Do not permit scoped/local IPv6 address syntax.
            ipaddress.IPv6Address(host)
            host = f"[{host.lower()}]"
        else:
            if parsed.netloc.startswith("["):
                raise ValueError  # IPvFuture is not a supported browser authority here.
            # Validate IDNs, but do not apply Python's IDNA2003 mapping to the URL:
            # e.g. faß.de must not silently become the different host fass.de.
            ascii_host = host.encode("idna").decode("ascii").lower()
            dns = ascii_host[:-1] if ascii_host.endswith(".") else ascii_host
            if len(dns) > 253 or not all(_LABEL.fullmatch(label) for label in dns.split(".")):
                raise ValueError
        default_port = 80 if scheme == "http" else 443
        authority = host if port in (None, default_port) else f"{host}:{port}"
    except (ValueError, UnicodeError) as exc:
        raise ValidationError("URL requires a valid host/port and no user information") from exc
    # urlunsplit drops empty ?/# delimiters, which can identify distinct resources.
    tail = value[len(parsed.scheme) + 3 + len(parsed.netloc) :]
    return f"{scheme}://{authority}{tail}"


def stable_game_id(provider_id: str, source_url: str) -> UUID:
    return uuid5(
        CATALOG_NAMESPACE, f"{validate_provider_id(provider_id)}\n{canonicalize_url(source_url)}"
    )


@dataclass(frozen=True)
class Dimensions:
    width: int | None = None
    height: int | None = None
    evidence: DimensionEvidence = DimensionEvidence.UNKNOWN

    def __post_init__(self) -> None:
        if not isinstance(self.evidence, DimensionEvidence):
            raise ValidationError("Dimension evidence must be explicit")
        if self.width is None and self.height is None:
            if self.evidence != DimensionEvidence.UNKNOWN:
                raise ValidationError("Unknown size must have unknown dimension evidence")
        elif (
            type(self.width) is not int
            or type(self.height) is not int
            or self.width <= 0
            or self.height <= 0
        ):
            raise ValidationError("Dimensions must be two positive integers or both unknown")
        elif self.evidence == DimensionEvidence.UNKNOWN:
            raise ValidationError("Known dimensions require an evidence category")

    @property
    def describes_game_size(self) -> bool:
        return self.evidence in (DimensionEvidence.DESIGN, DimensionEvidence.IFRAME)


@dataclass(frozen=True)
class CatalogItem:
    provider_id: str
    source_url: str
    source_name: str
    media_type: MediaType
    orientation: Orientation = Orientation.UNKNOWN
    dimensions: Dimensions = field(default_factory=Dimensions)
    launch_url: str | None = None

    def __post_init__(self) -> None:
        validate_provider_id(self.provider_id)
        if not isinstance(self.source_name, str) or not self.source_name.strip():
            raise ValidationError("Source name cannot be empty")
        if not isinstance(self.media_type, MediaType) or not isinstance(
            self.orientation, Orientation
        ):
            raise ValidationError("Media type and orientation must use domain enums")
        if not isinstance(self.dimensions, Dimensions):
            raise ValidationError("Dimensions must include source evidence")
        object.__setattr__(self, "source_url", canonicalize_url(self.source_url))
        if self.launch_url is not None:
            object.__setattr__(self, "launch_url", canonicalize_url(self.launch_url))

    @property
    def game_id(self) -> UUID:
        return stable_game_id(self.provider_id, self.source_url)

    @property
    def playable_url(self) -> str:
        return self.launch_url if self.launch_url is not None else self.source_url
