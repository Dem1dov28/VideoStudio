"""FastGen Image tab settings: provider + model (UI and HTTP API mapping)."""

from __future__ import annotations

import re

from config import settings

DEFAULT_IMAGE_PROVIDER_UI = "Flow"
DEFAULT_IMAGE_MODEL_UI = "Nano Banana Pro"

# v2 media_gen_api enums (see fast-gen.ai OpenAPI / hidden <select> values).
DEFAULT_IMAGE_PROVIDER_API = "flow"
DEFAULT_IMAGE_MODEL_API = "GEM_PIX_2"  # Nano Banana Pro


def resolve_fastgen_image_provider_ui() -> str:
    raw = (
        getattr(settings, "fastgen_image_provider", None)
        or DEFAULT_IMAGE_PROVIDER_UI
    ).strip()
    return raw or DEFAULT_IMAGE_PROVIDER_UI


def resolve_fastgen_image_model_ui() -> str:
    raw = (getattr(settings, "fastgen_model", None) or DEFAULT_IMAGE_MODEL_UI).strip()
    return raw or DEFAULT_IMAGE_MODEL_UI


def resolve_fastgen_image_provider_api() -> str:
    """Map UI provider label → API provider slug for v2 /images."""
    raw = resolve_fastgen_image_provider_ui()
    token = re.sub(r"[^A-Za-z0-9]+", "_", raw).lower().strip("_")
    if token in ("flow",):
        return "flow"
    if token in ("google_fx", "google", "fx"):
        return "google_fx"
    return token or DEFAULT_IMAGE_PROVIDER_API


def resolve_fastgen_image_model_api(*, prompt: str | None = None) -> str:
    """
    Map FASTGEN_MODEL (UI label or legacy enum) → v2 images API model field.
    Ignores old Mode5 overrides — model comes from settings everywhere.
    """
    _ = prompt  # reserved; no per-prompt overrides anymore
    raw = resolve_fastgen_image_model_ui()
    compact = re.sub(r"[^A-Za-z0-9]+", "_", raw).upper().strip("_")
    if not compact:
        return DEFAULT_IMAGE_MODEL_API
    if compact in ("GEM_PIX_2", "GEMPIX2", "PIX_2"):
        return "GEM_PIX_2"
    if compact in ("NARWHAL", "NANO_BANANA_2", "BANANA_2"):
        return "NARWHAL"
    if "IMAGEN" in compact:
        return "IMAGEN_4" if "4" in compact else "IMAGEN_3"
    if "BANANA" in compact and "PRO" in compact:
        return "GEM_PIX_2"
    if "BANANA" in compact and "2" in compact:
        return "NARWHAL"
    u = raw.upper().replace(" ", "").replace("_", "").replace("-", "")
    if u in ("GEMPIX2", "GEMPIX"):
        return "GEM_PIX_2"
    if u in ("NARWHAL", "NANOBANANA2"):
        return "NARWHAL"
    return DEFAULT_IMAGE_MODEL_API
