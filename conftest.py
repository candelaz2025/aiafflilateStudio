"""Shared test setup: provider tests exercise every video model, so open them all by default.

Tests for the production default (OpenRouter Veo 3.1 Lite only) delete this variable themselves.
"""
import pytest


@pytest.fixture(autouse=True)
def _all_video_models(monkeypatch):
    monkeypatch.setenv('ENABLED_VIDEO_MODELS', 'all')
