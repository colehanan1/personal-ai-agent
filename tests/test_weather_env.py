import logging

from integrations import weather as weather_module


def _reset_warning_flag() -> None:
    weather_module._LEGACY_KEY_WARNING_EMITTED = False


def test_weather_api_prefers_openweather(monkeypatch, caplog):
    _reset_warning_flag()
    monkeypatch.setenv("OPENWEATHER_API_KEY", "open-key")
    monkeypatch.setenv("WEATHER_API_KEY", "legacy-key")

    caplog.set_level(logging.WARNING)

    weather = weather_module.WeatherAPI()

    assert weather.api_key == "open-key"
    assert not any(
        "WEATHER_API_KEY is deprecated" in record.message
        for record in caplog.records
    )


def test_weather_api_legacy_fallback_warns_once(monkeypatch, caplog):
    _reset_warning_flag()
    monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)
    monkeypatch.setenv("WEATHER_API_KEY", "legacy-key")

    caplog.set_level(logging.WARNING)

    weather_module.WeatherAPI()
    weather_module.WeatherAPI()

    warnings = [
        record
        for record in caplog.records
        if "WEATHER_API_KEY is deprecated" in record.message
    ]
    assert len(warnings) == 1
