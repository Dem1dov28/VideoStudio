"""FastGen image provider + model mapping (Flow / Nano Banana Pro)."""

from agents.content_generator.fastgen_image_config import (
    resolve_fastgen_image_model_api,
    resolve_fastgen_image_model_ui,
    resolve_fastgen_image_provider_api,
    resolve_fastgen_image_provider_ui,
)


def test_ui_labels_from_settings():
    provider = resolve_fastgen_image_provider_ui()
    model = resolve_fastgen_image_model_ui()
    assert provider
    assert model


def test_api_mapping_nano_banana_pro():
    from config import settings

    old_model = settings.fastgen_model
    old_provider = settings.fastgen_image_provider
    try:
        settings.fastgen_image_provider = "Flow"
        settings.fastgen_model = "Nano Banana Pro"
        assert resolve_fastgen_image_model_api() == "GEM_PIX_2"
        assert resolve_fastgen_image_provider_api() == "flow"
    finally:
        settings.fastgen_model = old_model
        settings.fastgen_image_provider = old_provider


def test_legacy_narwhal_alias():
    from config import settings

    old = settings.fastgen_model
    try:
        settings.fastgen_model = "NARWHAL"
        assert resolve_fastgen_image_model_api() == "NARWHAL"
        settings.fastgen_model = "Nano Banana 2"
        assert resolve_fastgen_image_model_api() == "NARWHAL"
    finally:
        settings.fastgen_model = old
