#!/usr/bin/env python3
"""Download a LongPT torrent and add it to qBittorrent for seeding."""

import argparse
import html
import os
import re
from pathlib import Path
from urllib.parse import unquote, urljoin

import requests

from longpt_publish import load_env_file


LONGPT_BASE_URL = 'https://longpt.org/'


def sanitize_filename(value):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', value).strip(' .') or 'longpt.torrent'


def require_env(name):
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f'缺少 {name}。请写入 .env 后重试。')
    return value


def extract_torrent_id(value):
    match = re.search(r'(?:id|torrentid)=(\d+)', value or '')
    if match:
        return match.group(1)
    if value and value.isdigit():
        return value
    return ''


def make_longpt_session(cookie):
    session = requests.Session()
    session.headers.update({
        'Cookie': cookie,
        'Referer': urljoin(LONGPT_BASE_URL, 'torrents.php'),
        'User-Agent': 'publish-helper/longpt-seed',
    })
    return session


def find_download_url(details_html, details_url, torrent_id):
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', details_html, re.IGNORECASE)
    for href in hrefs:
        href = html.unescape(href)
        if 'download.php' in href.lower():
            return urljoin(details_url, href)

    if torrent_id:
        return urljoin(LONGPT_BASE_URL, f'download.php?id={torrent_id}')
    return ''


def filename_from_response(response, torrent_id):
    disposition = response.headers.get('Content-Disposition', '')
    match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', disposition, re.IGNORECASE)
    if match:
        return sanitize_filename(unquote(html.unescape(match.group(1))))
    if torrent_id:
        return f'longpt_{torrent_id}.torrent'
    return 'longpt.torrent'


def assert_torrent_response(response):
    body_start = response.content[:256].lstrip()
    if not body_start.startswith(b'd'):
        text = response.text[:300] if response.encoding else response.content[:300].decode('utf-8', 'ignore')
        raise RuntimeError(f'下载结果不像 .torrent，可能 cookie 失效或没有权限。响应开头: {text!r}')


def download_torrent(details_or_id, output_dir):
    cookie = require_env('LONGPT_COOKIE')
    session = make_longpt_session(cookie)

    torrent_id = extract_torrent_id(details_or_id)
    if details_or_id.startswith('http'):
        details_url = details_or_id
    elif torrent_id:
        details_url = urljoin(LONGPT_BASE_URL, f'details.php?id={torrent_id}')
    else:
        raise SystemExit('请传入 LongPT 详情页 URL 或种子 id。')

    details_response = session.get(details_url, timeout=30)
    details_response.raise_for_status()
    download_url = find_download_url(details_response.text, details_url, torrent_id)
    if not download_url:
        raise RuntimeError('没有在详情页找到 download.php 链接。')

    torrent_response = session.get(download_url, timeout=60)
    torrent_response.raise_for_status()
    assert_torrent_response(torrent_response)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    filename = filename_from_response(torrent_response, torrent_id)
    torrent_path = output_path / filename
    torrent_path.write_bytes(torrent_response.content)
    return torrent_path, details_url, download_url


def qbit_url(base_url, path):
    return urljoin(base_url.rstrip('/') + '/', path.lstrip('/'))


def qbit_login(session, base_url, username, password):
    if not username and not password:
        return

    response = session.post(
        qbit_url(base_url, '/api/v2/auth/login'),
        data={'username': username or '', 'password': password or ''},
        timeout=15,
    )
    if response.status_code == 403:
        raise RuntimeError('qBittorrent WebUI 返回 403，请检查 WebUI 认证、Host Header 校验或本机访问白名单。')
    response.raise_for_status()
    if response.text.strip() != 'Ok.':
        raise RuntimeError(f'qBittorrent 登录失败: {response.text[:200]}')


def add_to_qbit(torrent_path, savepath, skip_checking=True):
    base_url = os.environ.get('QBIT_URL', 'http://127.0.0.1:8086')
    username = os.environ.get('QBIT_USERNAME', '')
    password = os.environ.get('QBIT_PASSWORD', '')

    session = requests.Session()
    qbit_login(session, base_url, username, password)

    data = {
        'savepath': savepath,
        'paused': 'false',
        'root_folder': 'true',
        'skip_checking': 'true' if skip_checking else 'false',
    }
    with open(torrent_path, 'rb') as torrent_file:
        files = {
            'torrents': (Path(torrent_path).name, torrent_file, 'application/x-bittorrent'),
        }
        response = session.post(
            qbit_url(base_url, '/api/v2/torrents/add'),
            data=data,
            files=files,
            timeout=30,
        )

    if response.status_code == 403:
        raise RuntimeError('qBittorrent WebUI 返回 403。需要 .env 里的 QBIT_USERNAME/QBIT_PASSWORD，或在 WebUI 设置里允许本机免认证。')
    response.raise_for_status()
    if response.text and response.text.strip().lower() not in {'ok.', 'ok'}:
        raise RuntimeError(f'qBittorrent 添加失败: {response.text[:200]}')


def main():
    parser = argparse.ArgumentParser(description='Download LongPT torrent and add it to qBittorrent')
    parser.add_argument('details_or_id', help='LongPT details URL or torrent id')
    parser.add_argument('--output-dir', default='temp/torrent/downloaded')
    parser.add_argument('--qbit-add', action='store_true', help='Add downloaded torrent to qBittorrent')
    parser.add_argument('--savepath', default=r'C:\download\iqy')
    parser.add_argument('--no-skip-checking', action='store_true')
    args = parser.parse_args()

    load_env_file()

    try:
        torrent_path, details_url, download_url = download_torrent(args.details_or_id, args.output_dir)
        print(f'详情页: {details_url}')
        print('下载链接: 已从详情页解析')
        print(f'种子已下载: {torrent_path}')

        if args.qbit_add:
            add_to_qbit(torrent_path, args.savepath, skip_checking=not args.no_skip_checking)
            print(f'已添加到 qBittorrent: savepath={args.savepath}, skip_checking={not args.no_skip_checking}')
    except (requests.RequestException, RuntimeError) as exc:
        raise SystemExit(str(exc)) from exc

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
