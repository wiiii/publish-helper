# Publish Helper 打包指南

## 快速开始

### 一键打包

在项目根目录下运行其中一个脚本：

```bat
build.bat
```

或使用 PowerShell：

```powershell
.\build.ps1
```

打包完成后，可执行文件会生成在：

```text
dist\Publish Helper.exe
```

## 手动打包

### 1. 安装依赖

确保已安装 Python 3.9 或更高版本，然后安装依赖：

```bash
pip install -r requirements.txt
pip install pyinstaller
```

### 2. 执行 PyInstaller

在项目根目录下执行：

```bash
pyinstaller --clean publish-helper.spec
```

## PyInstaller 配置

`publish-helper.spec` 是本项目的打包配置，主要内容包括：

- 入口文件：`src/main_gui.py`
- 输出文件：`dist\Publish Helper.exe`
- 程序图标：`static/ph-bjd.ico`
- 数据文件：`static`、`media`、`temp`、`Mandarin.dat` 等
- 隐藏导入：GUI、API、核心工具等动态导入模块
- 排除项：`PyQt5`、`PySide2`、`PySide6` 等非项目使用的 Qt 绑定

项目源码使用 `PyQt6`。如果构建环境中同时安装了 `PyQt5`，PyInstaller 可能会报 “attempt to collect multiple Qt bindings packages”，当前 spec 文件已通过 `excludes` 固定只收集 `PyQt6`。

## 常见问题

### Q1: 打包时报多个 Qt 绑定冲突

确认使用仓库中的 `publish-helper.spec` 打包：

```bash
pyinstaller --clean publish-helper.spec
```

不要直接用 `pyinstaller src/main_gui.py` 生成临时 spec，否则可能重新扫描到环境里的 `PyQt5`。

### Q2: 打包后找不到 EXE

当前配置生成单文件 EXE，路径是：

```text
dist\Publish Helper.exe
```

不是 `dist\Publish Helper\Publish Helper.exe`。

### Q3: 打包后运行闪退

可以先检查：

1. 依赖是否完整安装
2. `publish-helper.spec` 中的 `datas` 是否包含必要资源
3. 杀毒软件是否拦截生成的 EXE
4. 是否需要临时把 `console=False` 改为 `console=True` 查看错误输出

### Q4: 缺少某些模块

在 `publish-helper.spec` 的 `hiddenimports` 中添加缺失模块，然后重新打包。

## 自定义

### 修改图标

编辑 `publish-helper.spec`：

```python
icon='static/ph-bjd.ico',
```

### 添加数据文件

编辑 `publish-helper.spec` 的 `datas`：

```python
datas=[
    ('你的文件夹', '目标文件夹'),
]
```

### 修改输出名称

编辑 `publish-helper.spec` 的 `name`：

```python
name='Publish Helper',
```

## 测试建议

打包完成后建议检查：

1. `dist\Publish Helper.exe` 是否存在
2. 程序界面是否能正常打开
3. 核心发布、重命名、截图、媒体信息等功能是否可用
4. 在未安装 Python 的 Windows 环境中是否能运行

## 注意事项

1. 首次启动可能较慢，这是 PyInstaller 单文件程序的正常现象。
2. 建议在干净虚拟环境中打包，减少无关依赖被扫描。
3. 打包前确认源码可以直接运行。
4. `build` 和 `dist` 是构建产物，不需要提交到仓库。
