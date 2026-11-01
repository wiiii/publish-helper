import json

import pytest

from src.core import rename
from src.core.platforms import get_platform, load_platforms, save_platform_templates


@pytest.fixture
def platform_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def render_name(monkeypatch, template, platform='', source='WEB-DL', key='file_name_movie'):
    monkeypatch.setattr(rename, 'get_settings', lambda setting: template)
    return rename.get_name_from_template(
        'Example', '示例', '01', '{集数}', '2026', '2160p', source,
        'H.265', '10bit', 'HDR10', '', 'DDP', '5.1', '', 'LongWeb',
        '', '1', '全2集', '网络收费短剧', '剧情', '演员', key, platform=platform,
    )


@pytest.mark.parametrize('platform, expected', [
    ('爱奇艺', 'iQIYI'), ('netflix', 'NF'), (' DisneyPlus ', 'DSNP'),
    ('腾讯视频', 'Tencent'), ('自定义台', '自定义台'), ('', ''),
])
def test_platform_names_and_aliases(platform_workspace, platform, expected):
    assert get_platform(platform)[0] == expected
    assert not (platform_workspace / 'static/platforms.json').exists()


@pytest.mark.parametrize('media_type', ['movie', 'tv', 'playlet'])
@pytest.mark.parametrize('kind, separator', [('file_name', '.'), ('main_title', ' ')])
def test_inherited_templates_add_platform(platform_workspace, monkeypatch, media_type, kind, separator):
    result = render_name(
        monkeypatch, separator.join(['{en_title}', '{platform}', '{source}', '{video_codec}']),
        '爱奇艺', key=f'{kind}_{media_type}',
    )
    assert result == separator.join(['Example', 'iQIYI', 'WEB-DL', 'H.265'])
    result = render_name(
        monkeypatch, separator.join(['{en_title}', '{source}', '{video_codec}']),
        '爱奇艺', key=f'{kind}_{media_type}',
    )
    assert result == separator.join(['Example', 'iQIYI', 'WEB-DL', 'H.265'])


@pytest.mark.parametrize('platform, source', [
    ('DisneyPlus', 'DSNP WEB-DL'), ('DSNP', 'DisneyPlus WEB-DL'),
    ('Netflix', 'nf WEB-DL'), ('爱奇艺', 'iQIYI WEB-DL'),
])
def test_platform_already_in_source_is_not_repeated(platform_workspace, monkeypatch, platform, source):
    result = render_name(monkeypatch, '{en_title}.{platform}.{source}', platform, source)
    assert result == 'Example.' + get_platform(platform)[0] + '.WEB-DL'


def test_platform_detection_does_not_match_inside_another_word(platform_workspace, monkeypatch):
    result = render_name(monkeypatch, '{en_title}.{platform}.{source}', 'NF', 'INF WEB-DL')
    assert result == 'Example.NF.INF.WEB-DL'


def test_platform_is_kept_when_template_does_not_include_source(platform_workspace, monkeypatch):
    result = render_name(monkeypatch, '{en_title}.{platform}', 'NF', 'NF WEB-DL')
    assert result == 'Example.NF'


def test_generic_templates_keep_existing_behavior(platform_workspace, monkeypatch):
    result = render_name(monkeypatch, '{en_title}.{platform}.{source}')
    assert result == 'Example.WEB-DL'
    assert render_name(monkeypatch, '{platform}') == ''


def test_partial_overrides_inherit_and_reload(platform_workspace, monkeypatch):
    save_platform_templates('爱奇艺', {'file_name_movie': '{platform}.{en_title}.{hdr_format}.{video_codec}'})
    assert render_name(monkeypatch, '{en_title}.{source}', 'iQIYI') == 'iQIYI.Example.HDR10.H.265'
    assert render_name(monkeypatch, '{en_title} {source}', 'iQIYI', key='main_title_movie') == 'Example iQIYI WEB-DL'
    assert render_name(monkeypatch, '{en_title}.{source}', 'Tencent') == 'Example.Tencent.WEB-DL'
    save_platform_templates('iQIYI', {'file_name_movie': '{en_title}.{source}'})
    assert render_name(monkeypatch, '{en_title}.{source}', 'iQIYI') == 'Example.WEB-DL'
    save_platform_templates('iQIYI', {})
    assert render_name(monkeypatch, '{en_title}.{source}', 'iQIYI') == 'Example.iQIYI.WEB-DL'


def test_platform_code_and_display_name_placeholders(platform_workspace, monkeypatch):
    result = render_name(
        monkeypatch, '{en_title}.{video_format}.{platform_code}.{source}', '爱奇艺',
    )
    assert result == 'Example.2160p.IQY.WEB-DL'
    result = render_name(
        monkeypatch, '{platform_name} | {en_title}', 'Tencent', key='second_title_tv',
    )
    assert result == '腾讯视频 | Example'
    result = render_name(monkeypatch, '{en_title}.{platform_name}.{source}', '优酷')
    assert result == 'Example.优酷.WEB-DL'
    # 自定义平台没配短码时退回平台名，不留空
    assert render_name(monkeypatch, '{platform_code}', '自定义台') == '自定义台'


def test_platform_code_placeholder_does_not_duplicate_brand(platform_workspace, monkeypatch):
    result = render_name(monkeypatch, '{en_title}.{platform_code}.{source}', 'NF')
    assert result == 'Example.NF.WEB-DL'


def test_custom_platform_can_override_code_and_display_name(platform_workspace):
    save_platform_templates('Netflix', {'file_name_movie': '{platform_code}.{en_title}'})
    profiles = load_platforms()
    assert profiles['NF']['code'] == 'NF'
    assert profiles['NF']['display_name'] == 'Netflix'


def test_tv_episode_placeholder_and_playlet_source_are_independent(platform_workspace, monkeypatch):
    save_platform_templates('NF', {
        'file_name_tv': '{en_title}.S{season}E{episode}.{platform}.{source}',
        'second_title_playlet': '{platform} | {playlet_source}',
    })
    assert render_name(monkeypatch, '', 'NF', key='file_name_tv') == 'Example.S01E{集数}.NF.WEB-DL'
    assert render_name(monkeypatch, '', 'NF', key='second_title_playlet') == 'NF | 网络收费短剧'


@pytest.mark.parametrize('templates', [
    {'unknown_template': '{en_title}'}, {'file_name_movie': '{platfrom}'},
    {'file_name_movie': '{en_title'}, {'file_name_movie': ''},
    {'file_name_movie': 123},
])
def test_invalid_rules_do_not_overwrite_valid_config(platform_workspace, templates):
    save_platform_templates('NF', {'file_name_movie': '{en_title}.{platform}'})
    config_path = platform_workspace / 'static/platforms.json'
    previous = config_path.read_bytes()
    with pytest.raises(ValueError):
        save_platform_templates('NF', templates)
    assert config_path.read_bytes() == previous


def test_alias_conflicts_are_rejected(platform_workspace):
    config_path = platform_workspace / 'static/platforms.json'
    config_path.parent.mkdir()
    config_path.write_text(json.dumps({'Other': {'aliases': ['Netflix'], 'templates': {}}}), encoding='utf-8')
    with pytest.raises(ValueError, match='别名重复'):
        load_platforms()


@pytest.mark.parametrize('content', ['{bad json', '[]', '{"NF": {"templates": []}}'])
def test_invalid_configuration_reports_error(platform_workspace, content):
    config_path = platform_workspace / 'static/platforms.json'
    config_path.parent.mkdir()
    config_path.write_text(content, encoding='utf-8')
    with pytest.raises(ValueError):
        get_platform('NF')
    assert get_platform('')[0] == ''


def test_custom_platform_save_keeps_other_profiles(platform_workspace):
    save_platform_templates('Custom', {'file_name_tv': '{en_title}.{platform}'})
    save_platform_templates('Netflix', {'second_title_movie': '{platform} {original_title}'})
    profiles = load_platforms()
    assert profiles['Custom']['templates']['file_name_tv'] == '{en_title}.{platform}'
    assert profiles['NF']['templates']['second_title_movie'] == '{platform} {original_title}'
