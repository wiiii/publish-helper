"""主窗口视觉规范：统一栅格、字号层级与按钮语义。

mainwindow.ui 由 Qt Designer 生成，控件用绝对几何 + 分散的嵌套 layout 摆放，
同一个表单里会出现多种标签起点、字段右边缘不齐、字号从 9pt 跳到 16pt 的情况。

本模块在 setupUi() 之后按统一栅格重建三个页面的布局：

* 标签列固定 74px、右对齐，字段统一从同一 x 起点开始
* 行距 8px、字段组间距 10px、区块间距 14px
* 字号收敛为三级：窗口标题 17pt / 区块标题 12pt / 标签正文 9.5pt
* 按钮只有三种形态：primary（实心绿）、secondary（描边）、cta（底部主操作）

所有 objectName 保持不变，业务代码（startgui.py 里 700+ 处控件引用）无需改动。
"""

import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QGuiApplication
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

ACCENT = "#12A97E"
ACCENT_DARK = "#0F9A73"
ACCENT_PRESSED = "#0C8060"

LABEL_W = 74
INPUT_H = 30
BTN_H = 30
ROW_GAP = 8
COL_GAP = 10
GROUP_GAP = 14
TITLE_PT = 12
WINDOW_TITLE_PT = 17

# 下拉箭头：Qt 一旦接管 QComboBox::drop-down 就不再绘制原生箭头，
# 而平台下拉框是可编辑的（点输入区只会进入编辑态），没有箭头就等于拉不开。
def _chevron_path():
    candidates = []
    base = Path(__file__).resolve()
    if len(base.parents) > 3:
        candidates.append(base.parents[3] / "static" / "ui" / "chevron-down.png")
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "static" / "ui" / "chevron-down.png")
    candidates.append(Path.cwd() / "static" / "ui" / "chevron-down.png")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


_CHEVRON = _chevron_path()
if _CHEVRON is not None:
    _CHEVRON_RULE = (
        "QComboBox::drop-down {\n"
        "    subcontrol-origin: padding;\n"
        "    subcontrol-position: center right;\n"
        "    width: 24px;\n"
        "    border: none;\n"
        "    background: transparent;\n"
        "}\n"
        "QComboBox::down-arrow {\n"
        f'    image: url("{_CHEVRON.as_posix()}");\n'
        "    width: 24px;\n"
        "    height: 24px;\n"
        "}\n"
    )
else:  # 资源缺失时退回原生箭头，宁可不好看也不能点不开
    _CHEVRON_RULE = ""

QSS = f"""
QWidget {{ font-family: "微软雅黑"; }}
QLabel {{ color: #2F3B45; background: transparent; }}
QLabel[role="section"] {{
    color: #26343F;
    border-bottom: 1px solid #E6EBEF;
    padding-bottom: 6px;
}}
QLabel[role="hint"] {{ color: #6B7B88; }}
QLineEdit, QComboBox, QSpinBox, QTextEdit, QTextBrowser {{
    background: #FFFFFF;
    border: 1px solid #DCE3E8;
    border-radius: 6px;
    padding: 3px 8px;
    color: #2F3B45;
}}
QTextEdit, QTextBrowser {{ background: #FBFDFE; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
QTextEdit:focus, QTextBrowser:focus {{ border-color: {ACCENT}; }}
{_CHEVRON_RULE}QComboBox QAbstractItemView {{
    border: 1px solid #DCE3E8;
    border-radius: 6px;
    background: #FFFFFF;
    selection-background-color: {ACCENT};
    selection-color: #FFFFFF;
    outline: 0;
    padding: 2px;
}}
QComboBox QAbstractItemView::item {{ min-height: 26px; padding-left: 6px; }}
QPushButton[variant="primary"] {{
    background: {ACCENT}; color: #FFFFFF; border: none; border-radius: 6px;
    padding: 3px 14px;
}}
QPushButton[variant="primary"]:hover {{ background: {ACCENT_DARK}; }}
QPushButton[variant="primary"]:pressed {{ background: {ACCENT_PRESSED}; }}
QPushButton[variant="secondary"] {{
    background: #FFFFFF; color: #2F3B45; border: 1px solid #DCE3E8;
    border-radius: 6px; padding: 3px 12px;
}}
QPushButton[variant="secondary"]:hover {{
    border-color: {ACCENT}; color: {ACCENT_DARK};
}}
QPushButton[variant="cta"] {{
    background: {ACCENT}; color: #FFFFFF; border: none; border-radius: 8px;
    font-size: 12pt; font-weight: 500;
}}
QPushButton[variant="cta"]:hover {{ background: {ACCENT_DARK}; }}
QPushButton[variant="cta"]:pressed {{ background: {ACCENT_PRESSED}; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{
    background: transparent; color: #6B7B88; padding: 7px 18px; font-size: 10pt;
    border: none; border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {ACCENT_DARK}; border-bottom: 2px solid {ACCENT}; }}
QTabBar::tab:hover {{ color: #2F3B45; }}
QCheckBox {{ color: #3A4B58; spacing: 5px; }}
"""


def _font(point_size, weight=QFont.Weight.Normal):
    font = QFont("微软雅黑")
    font.setPointSizeF(point_size)
    font.setWeight(weight)
    return font


def _widgets(page):
    return {w.objectName(): w for w in page.findChildren(QWidget) if w.objectName()}


def _find(page, cls, prefix):
    for widget in page.findChildren(cls):
        text = widget.text() if hasattr(widget, "text") else ""
        if text.startswith(prefix):
            return widget
    raise LookupError(f"{cls.__name__} starting with {prefix!r} not found")


def _section(label):
    label.setProperty("role", "section")
    label.setFont(_font(TITLE_PT, QFont.Weight.Medium))
    label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
    return label


def _hint(label):
    label.setProperty("role", "hint")
    label.setFont(_font(9.5))
    label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    return label


def _label(label):
    if label is None:
        return None
    label.setFont(_font(9.5))
    label.setFixedWidth(LABEL_W)
    label.setAlignment(
        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
    )
    return label


def _input(widget, height=INPUT_H):
    widget.setFixedHeight(height)
    widget.setFont(_font(9.5))
    widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return widget


def _combo(widget):
    _input(widget)
    widget.setMinimumWidth(120)
    widget.setSizeAdjustPolicy(
        QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
    )
    widget.setMinimumContentsLength(6)
    return widget


def _spin(widget):
    _input(widget)
    widget.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    return widget


def _button(widget, variant="secondary", height=BTN_H, full=False):
    widget.setProperty("variant", variant)
    widget.setFixedHeight(height)
    widget.setFont(_font(9.5))
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    policy = QSizePolicy.Policy.Expanding if full else QSizePolicy.Policy.Fixed
    widget.setSizePolicy(policy, QSizePolicy.Policy.Fixed)
    if not full:
        widget.setMinimumWidth(max(widget.sizeHint().width(), 64))
    return widget


def _apply_variant(widget):
    # 动态属性在 polish 之前设置，这里保险再刷一次样式
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def _fields_box(fields):
    box = QWidget()
    layout = QHBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    for field in fields:
        layout.addWidget(field)
    return box


def _form(rows, npairs=2):
    """rows: 每行是若干 (label, [fields], span) 三元组，span 以「标签+字段」为一对计。"""
    grid = QGridLayout()
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(COL_GAP)
    grid.setVerticalSpacing(ROW_GAP)
    for index in range(npairs):
        grid.setColumnMinimumWidth(index * 2, LABEL_W)
        grid.setColumnStretch(index * 2 + 1, 1)

    for row_index, row in enumerate(rows):
        column = 0
        for label, fields, span in row:
            if label is not None:
                _label(label)
                grid.addWidget(label, row_index, column)
            grid.addWidget(
                _fields_box(fields), row_index, column + 1, 1, span * 2 - 1
            )
            column += span * 2
    return grid


def _group(title, body, spacing=10, extra=None):
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(spacing)

    if extra is None:
        layout.addWidget(_section(title))
    else:
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        header.addWidget(_section(title), 1)
        header.addWidget(extra, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(header)

    if isinstance(body, QWidget):
        layout.addWidget(body, 1)
    else:
        layout.addLayout(body, 1)
    return box


def _reset(page):
    """摘掉旧的布局内容，返回承载新布局的容器。"""
    for widget in page.findChildren(QWidget):
        widget.hide()

    old = page.layout()
    if old is None:
        old = QVBoxLayout(page)
    else:
        while old.count():
            old.takeAt(0)
    old.setContentsMargins(16, 8, 16, 10)
    old.setSpacing(GROUP_GAP)

    content = QWidget(page)
    old.addWidget(content)
    return content


def _shell(page):
    content = _reset(page)
    root = QVBoxLayout(content)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(GROUP_GAP)

    columns = QHBoxLayout()
    columns.setSpacing(18)
    left = QVBoxLayout()
    left.setSpacing(GROUP_GAP)
    right = QVBoxLayout()
    right.setSpacing(GROUP_GAP)
    columns.addLayout(left, 56)
    columns.addLayout(right, 44)
    root.addLayout(columns, 1)

    bottom = QHBoxLayout()
    bottom.setSpacing(GROUP_GAP)
    root.addLayout(bottom)

    return content, left, right, bottom


def _show_tree(content):
    """只显示重建后仍在容器里的控件，旧布局遗留的控件保持隐藏。"""
    for widget in content.findChildren(QWidget):
        widget.show()
    content.show()


def _build_movie(page):
    w = _widgets(page)
    content, left, right, bottom = _shell(page)

    platform_label = _find(page, QLabel, "平台")
    rule_button = _button(_find(page, QPushButton, "命名规则"), "secondary")

    w["label"].setText("资源链接:")
    w["resourceUrlMovie"].setPlaceholderText("豆瓣 / IMDb / TMDB 链接")

    form = _form(
        [
            [(w["label"], [_input(w["resourceUrlMovie"])], 2)],
            [
                (platform_label, [_combo(w["platformMovie"])], 1),
                (w["label_3"], [_combo(w["sourceMovie"])], 1),
            ],
            [(w["label_6"], [_combo(w["teamMovie"])], 1)],
            [
                (
                    w["label_2"],
                    [
                        _input(w["videoPathMovie"]),
                        _button(w["selectVideoButtonMovie"], "secondary"),
                        _button(w["selectVideoFolderButtonMovie"], "secondary"),
                        _button(w["makeTorrentButtonMovie"], "primary"),
                    ],
                    2,
                )
            ],
        ]
    )
    left.addWidget(_group(w["label_16"], form, extra=rule_button))

    w["descriptionBrowserMovie"].setFont(_font(9.5))
    left.addWidget(
        _group(
            w["label_11"],
            _stack(w["descriptionBrowserMovie"], _button(w["getPtGenButtonMovie"], "primary", 32, full=True)),
        ),
        1,
    )
    w["pictureUrlBrowserMovie"].setFont(_font(9.5))
    left.addWidget(
        _group(
            w["label_5"],
            _stack(w["pictureUrlBrowserMovie"], _button(w["getPictureButtonMovie"], "primary", 32, full=True)),
        ),
        1,
    )

    w["debugBrowserMovie"].setMinimumHeight(86)
    w["debugBrowserMovie"].setFont(_font(9))
    right.addWidget(_group(w["label_4"], w["debugBrowserMovie"]))
    right.addWidget(_naming_group(page, w, "Movie"))
    w["mediainfoBrowserMovie"].setMinimumHeight(86)
    w["mediainfoBrowserMovie"].setFont(_font(9))
    right.addWidget(
        _group(
            w["label_10"],
            _stack(w["mediainfoBrowserMovie"], _button(w["getMediaInfoButtonMovie"], "primary", 32, full=True)),
        ),
        1,
    )

    bottom.addWidget(_button(w["startButtonMovie"], "cta", 50, full=True), 1)
    bottom.addWidget(_button(w["autoFeedButtonMovie"], "cta", 50, full=True), 1)

    _show_tree(content)


def _build_tv(page):
    w = _widgets(page)
    content, left, right, bottom = _shell(page)

    platform_label = _find(page, QLabel, "平台")
    rule_button = _button(_find(page, QPushButton, "命名规则"), "secondary")

    w["label_46"].setText("资源链接:")
    w["resourceUrlTV"].setPlaceholderText("豆瓣 / IMDb / TMDB 链接")
    _hint(w["label_61"])

    form = _form(
        [
            [(w["label_46"], [_input(w["resourceUrlTV"])], 2)],
            [
                (platform_label, [_combo(w["platformTV"])], 1),
                (w["label_47"], [_combo(w["sourceTV"])], 1),
            ],
            [
                (w["label_48"], [_combo(w["teamTV"])], 1),
                (w["label_58"], [_spin(w["seasonBoxTV"])], 1),
            ],
            [(w["label_60"], [_spin(w["episodesStartBoxTV"]), w["label_61"]], 1)],
            [
                (
                    w["label_49"],
                    [
                        _input(w["videoPathTV"]),
                        _button(w["selectVideoFolderButtonTV"], "secondary"),
                        _button(w["makeTorrentButtonTV"], "primary"),
                    ],
                    2,
                )
            ],
        ]
    )
    left.addWidget(_group(w["label_45"], form, extra=rule_button))

    w["descriptionBrowserTV"].setFont(_font(9.5))
    left.addWidget(
        _group(
            w["label_50"],
            _stack(w["descriptionBrowserTV"], _button(w["getPtGenButtonTV"], "primary", 32, full=True)),
        ),
        1,
    )
    w["pictureUrlBrowserTV"].setFont(_font(9.5))
    left.addWidget(
        _group(
            w["label_51"],
            _stack(w["pictureUrlBrowserTV"], _button(w["getPictureButtonTV"], "primary", 32, full=True)),
        ),
        1,
    )

    w["debugBrowserTV"].setMinimumHeight(86)
    w["debugBrowserTV"].setFont(_font(9))
    right.addWidget(_group(w["label_52"], w["debugBrowserTV"]))
    right.addWidget(_naming_group(page, w, "TV"))
    w["mediainfoBrowserTV"].setMinimumHeight(86)
    w["mediainfoBrowserTV"].setFont(_font(9))
    right.addWidget(
        _group(
            w["label_57"],
            _stack(w["mediainfoBrowserTV"], _button(w["getMediaInfoButtonTV"], "primary", 32, full=True)),
        ),
        1,
    )

    bottom.addWidget(_button(w["startButtonTV"], "cta", 50, full=True), 1)
    bottom.addWidget(_button(w["autoFeedButtonTV"], "cta", 50, full=True), 1)

    _show_tree(content)


def _build_playlet(page):
    w = _widgets(page)
    content, left, right, bottom = _shell(page)

    platform_label = _find(page, QLabel, "平台")
    rule_button = _button(_find(page, QPushButton, "命名规则"), "secondary")
    _hint(w["label_63"])

    form = _form(
        [
            [
                (platform_label, [_combo(w["platformPlaylet"])], 1),
                (w["label_8"], [_input(w["originalNameEditPlaylet"])], 1),
            ],
            [
                (w["label_9"], [_input(w["yearEditPlaylet"])], 1),
                (w["label_18"], [_spin(w["seasonBoxPlaylet"])], 1),
            ],
            [
                (w["label_62"], [_spin(w["episodesStartBoxPlaylet"]), w["label_63"]], 1),
                (w["label_33"], [_combo(w["areaPlaylet"])], 1),
            ],
            [
                (w["label_32"], [_combo(w["languagePlaylet"])], 1),
                (w["label_19"], [_combo(w["playletSource"])], 1),
            ],
            [
                (w["label_20"], [_combo(w["sourcePlaylet"])], 1),
                (w["label_21"], [_combo(w["teamPlaylet"])], 1),
            ],
            [
                (
                    w["label_22"],
                    [
                        _input(w["videoPathPlaylet"]),
                        _button(w["selectVideoFolderButtonPlaylet"], "secondary"),
                        _button(w["makeTorrentButtonPlaylet"], "primary"),
                    ],
                    2,
                )
            ],
            [
                (
                    w["label_23"],
                    [
                        _input(w["coverPathPlaylet"]),
                        _button(w["selectCoverFolderButtonPlaylet"], "secondary"),
                        _button(w["uploadCoverButtonPlaylet"], "secondary"),
                    ],
                    2,
                )
            ],
            [(None, [_tag_grid(page)], 2)],
        ]
    )
    left.addWidget(_group(w["label_17"], form, extra=rule_button))

    w["descriptionBrowserPlaylet"].setFont(_font(9.5))
    left.addWidget(
        _group(
            w["label_24"],
            _stack(
                w["descriptionBrowserPlaylet"],
                _button(w["getDescriptionButtonPlaylet"], "primary", 32, full=True),
            ),
        ),
        1,
    )
    w["pictureUrlBrowserPlaylet"].setFont(_font(9.5))
    left.addWidget(
        _group(
            w["label_25"],
            _stack(
                w["pictureUrlBrowserPlaylet"],
                _button(w["getPictureButtonPlaylet"], "primary", 32, full=True),
            ),
        ),
        1,
    )

    w["debugBrowserPlaylet"].setMinimumHeight(86)
    w["debugBrowserPlaylet"].setFont(_font(9))
    right.addWidget(_group(w["label_26"], w["debugBrowserPlaylet"]))
    right.addWidget(_naming_group(page, w, "Playlet"))
    w["mediainfoBrowserPlaylet"].setMinimumHeight(86)
    w["mediainfoBrowserPlaylet"].setFont(_font(9))
    right.addWidget(
        _group(
            w["label_31"],
            _stack(
                w["mediainfoBrowserPlaylet"],
                _button(w["getMediaInfoButtonPlaylet"], "primary", 32, full=True),
            ),
        ),
        1,
    )

    bottom.addWidget(_button(w["startButtonPlaylet"], "cta", 50, full=True), 1)
    bottom.addWidget(_button(w["autoFeedButtonPlaylet"], "cta", 50, full=True), 1)

    _show_tree(content)


def _stack(editor, button):
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    layout.addWidget(editor, 1)
    layout.addWidget(button)
    return box


def _naming_group(page, w, suffix):
    labels = {
        "Movie": ("label_13", "label_14", "label_15"),
        "TV": ("label_54", "label_55", "label_56"),
        "Playlet": ("label_28", "label_29", "label_30"),
    }[suffix]
    editors = [
        w[f"mainTitleBrowser{suffix}"],
        w[f"secondTitleBrowser{suffix}"],
        w[f"fileNameBrowser{suffix}"],
    ]
    rows = []
    for label_name, editor in zip(labels, editors):
        editor.setMinimumHeight(52)
        editor.setFont(_font(9))
        rows.append([(w[label_name], [editor], 1)])

    title = {"Movie": "label_12", "TV": "label_53", "Playlet": "label_27"}[suffix]
    body = QWidget()
    layout = QVBoxLayout(body)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(ROW_GAP)
    layout.addLayout(_form(rows, npairs=1))
    layout.addWidget(_button(w[f"getNameButton{suffix}"], "primary", 32, full=True))
    return _group(w[title], body)


def _tag_grid(page):
    box = QWidget()
    grid = QGridLayout(box)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(14)
    grid.setVerticalSpacing(6)
    for index in range(16):
        checkbox = page.findChild(QCheckBox, f"checkBox_{index}")
        if checkbox is not None:
            checkbox.setFont(_font(9.5))
            grid.addWidget(checkbox, index // 8, index % 8)
    return box


def _size_window(win):
    """默认尺寸按屏幕可用区域收缩，避免小屏上一开窗就超出桌面。"""
    width, height = 1180, 830
    screen = win.screen() or QGuiApplication.primaryScreen()
    if screen is not None:
        available = screen.availableGeometry()
        width = min(width, max(960, available.width() - 80))
        height = min(height, max(700, available.height() - 80))
    win.resize(width, height)
    win.setMinimumSize(960, 700)


def _window_title(win):
    label = win.findChild(QLabel, "label_7")
    if label is None:
        return
    label.setFont(_font(WINDOW_TITLE_PT, QFont.Weight.Medium))
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)


def apply(win):
    """在 setupUi() 之后调用，重建主窗口的布局与样式。"""
    # mainwindow.ui 里散落着 28 处内联 styleSheet（绿色按钮等），
    # 它们的优先级高于窗口级样式表，必须清掉才能让统一规范生效
    for widget in win.findChildren(QWidget):
        if widget.styleSheet():
            widget.setStyleSheet("")

    win.setStyleSheet(QSS)
    _window_title(win)
    _size_window(win)

    tabs = win.findChild(QTabWidget, "tabWiget")
    if tabs is None:
        return

    builders = {"tab": _build_movie, "tab_2": _build_tv, "tab_3": _build_playlet}
    for index in range(tabs.count()):
        page = tabs.widget(index)
        builder = builders.get(page.objectName())
        if builder is not None:
            builder(page)

    for button in win.findChildren(QPushButton):
        _apply_variant(button)
