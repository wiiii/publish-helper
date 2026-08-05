# -*- mode: python ; coding: utf-8 -*-
import os
import platform

block_cipher = None

_system = platform.system()  # 'Windows' / 'Linux' / 'Darwin'

# 平台相关二进制文件：
# - Mandarin.dat 全平台都需要
# - libmediainfo.0.dylib 仅 macOS 存在，Windows/Linux 使用各自系统的 MediaInfo 库
binaries = [('Mandarin.dat', '.')]
if _system == 'Darwin':
    binaries.append(('libmediainfo.0.dylib', '.'))

# 图标：仅 Windows / macOS 需要；Linux 下 .ico 不被支持，留空
_app_icon = 'static/ph-bjd.ico' if _system in ('Windows', 'Darwin') else None

# 跨平台可执行文件名：Windows 保留带空格的 "Publish Helper"，
# Linux / macOS 使用无空格名称，便于在 shell / CI 中引用
_app_name = 'Publish Helper' if _system == 'Windows' else 'publish-helper'

# Linux 打包为无桌面依赖的 CLI 版（main_cli.py，console=True），
# Windows / macOS 仍为桌面 GUI 版（main_gui.py，console=False）
_entry = 'src/main_cli.py' if _system == 'Linux' else 'src/main_gui.py'
a = Analysis(
    [_entry],
    pathex=[],
    binaries=binaries,
    datas=[
        ('static', 'static'),
        ('docs/requirements.txt', 'docs'),
        ('media', 'media'),
        ('temp', 'temp'),
        ('Mandarin.dat', 'xpinyin'),
        ('LICENSE', '.'),
        ('README.md', '.'),
        ('readme.txt', '.'),
        ('.env.example', '.env.example'),
    ],
    hiddenimports=[
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'flask',
        'flask_cors',
        'requests',
        'PIL',
        'cv2',
        'numpy',
        'pymediainfo',
        'torf',
        'pyperclip',
        'xpinyin',
        'click',
        'colorama',
        'dotenv',
        'jinja2',
        'werkzeug',
        'prompt_toolkit',
        'src.gui.ui.mainwindow',
        'src.gui.ui.settings',
        'src.gui.ui.toast',
        'src.core.autofeed',
        'src.core.mediainfo',
        'src.core.picturebed',
        'src.core.poster',
        'src.core.ptgen',
        'src.core.rename',
        'src.core.screenshot',
        'src.core.tool',
        'src.api.startapi',
        'src.config.settings',
        'src.utils.logger',
        'src.utils.file_utils',
        'src.utils.exceptions',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PyQt5',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        'PySide2',
        'PySide6',
        'shiboken2',
        'shiboken6',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=_app_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=(_system == 'Linux'),
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_app_icon,
)
