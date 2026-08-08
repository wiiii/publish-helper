"""Tests for CLI rename-title confirmation."""

from src import main_cli
from src.core import rename


def _enable_rename_confirmation(monkeypatch):
    settings = {
        "rename_file": "True",
        "second_confirm_file_name": "True",
    }
    monkeypatch.setattr(main_cli, "get_settings", settings.get)


def test_prompt_rename_english_title_keeps_ptgen_name_on_enter(monkeypatch):
    _enable_rename_confirmation(monkeypatch)
    monkeypatch.setattr("builtins.input", lambda _: "")

    result = main_cli.prompt_rename_english_title("Bing Zi Feng Zhong Lai")

    assert result == "Bing Zi Feng Zhong Lai"


def test_custom_dotted_title_is_normalized_before_full_name_is_assembled(monkeypatch):
    _enable_rename_confirmation(monkeypatch)
    monkeypatch.setattr("builtins.input", lambda _: "Bing.Zi.Feng.Zhong.Lai")

    english_title = main_cli.prompt_rename_english_title("PTGen Title")
    monkeypatch.setattr(
        rename,
        "get_settings",
        lambda _: "{original_title}.{en_title}.{year}.{video_format}.{audio_codec}-{team}",
    )
    file_name = main_cli.get_name_from_template(
        english_title, "冰自风中来", "", "", "2026", "2160p", "WEB-DL",
        "H265", "10bit", "HDR10", "", "TrueHD", "7.1", "", "LongPT",
        "", "", "", "", "", "", "file_name_movie",
    )

    assert english_title == "Bing Zi Feng Zhong Lai"
    assert file_name == "冰自风中来.Bing.Zi.Feng.Zhong.Lai.2026.2160p.TrueHD-LongPT"


def test_prompt_rename_english_title_skips_prompt_when_rename_is_disabled(monkeypatch):
    monkeypatch.setattr(
        main_cli,
        "get_settings",
        {"rename_file": "", "second_confirm_file_name": "True"}.get,
    )

    def fail_if_prompted(_):
        raise AssertionError("input should not be called")

    monkeypatch.setattr("builtins.input", fail_if_prompted)

    assert main_cli.prompt_rename_english_title("Generated Title") == "Generated Title"
