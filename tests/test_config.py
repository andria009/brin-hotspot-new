from brin_hotspot.config import PathSettings, Settings


def test_settings_create_runtime_directories(tmp_path):
    settings = Settings(
        paths=PathSettings(
            input_dir=tmp_path / "input",
            output_dir=tmp_path / "output",
            log_dir=tmp_path / "logs",
        )
    )

    settings.ensure_runtime_directories()

    assert settings.paths.input_dir.is_dir()
    assert settings.paths.output_dir.is_dir()
    assert settings.paths.log_dir.is_dir()
