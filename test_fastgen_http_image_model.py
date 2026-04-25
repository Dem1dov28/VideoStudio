from agents.content_generator import fastgen_http
from config import settings


def test_mode5_pipeline_forces_gem_pix_2(monkeypatch):
    monkeypatch.setattr(settings, "pipeline_mode", "mode5")
    monkeypatch.setattr(settings, "fastgen_model", "NARWHAL")
    assert fastgen_http._resolve_image_model_for_prompt("any prompt") == "GEM_PIX_2"


def test_mode5_prompt_marker_forces_gem_pix_2(monkeypatch):
    monkeypatch.setattr(settings, "pipeline_mode", "mode1")
    monkeypatch.setattr(settings, "fastgen_model", "IMAGEN_3_5")
    prompt = "scene\n\nHard override for mode5: one dominant full-frame scene only."
    assert fastgen_http._resolve_image_model_for_prompt(prompt) == "GEM_PIX_2"


def test_non_mode5_keeps_normalized_model(monkeypatch):
    monkeypatch.setattr(settings, "pipeline_mode", "mode1")
    monkeypatch.setattr(settings, "fastgen_model", "IMAGEN_3_5")
    assert fastgen_http._resolve_image_model_for_prompt("generic scene prompt") == "GEM_PIX_2"


def test_v2_image_body_generate_mode5_uses_gem_pix_2(monkeypatch):
    monkeypatch.setattr(settings, "pipeline_mode", "mode5")
    monkeypatch.setattr(settings, "fastgen_model", "NARWHAL")
    body = fastgen_http._v2_image_body_generate("simple prompt")
    assert body["parameters"]["model"] == "GEM_PIX_2"


def test_v2_image_body_generate_disables_imagen_and_falls_back_to_gem_pix_2(monkeypatch):
    monkeypatch.setattr(settings, "pipeline_mode", "mode1")
    monkeypatch.setattr(settings, "fastgen_model", "IMAGEN_3_5")
    body = fastgen_http._v2_image_body_generate("simple prompt")
    assert body["parameters"]["model"] == "GEM_PIX_2"

