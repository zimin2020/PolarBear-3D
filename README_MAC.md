# macOS 打包指南 (Packaging Guide)

由于当前环境为 Windows，无法直接生成 macOS 可执行文件（PyInstaller 不支持跨平台打包）。

为了解决这个问题，我为您准备了两种方案：

## 方案 A：通过 GitHub Actions 自动化打包 (推荐)
我已经为您创建了 [macos-build.yml](file:///e:/程序/TRAE/4/.github/workflows/macos-build.yml) 自动化脚本。

1. 将代码上传到 GitHub。
2. 每次您推送 (Push) 代码时，GitHub 会自动启动一个苹果电脑云服务器为您打包。
3. 您可以在 GitHub 项目页面的 **Actions** 标签下下载生成的 `.dmg` 安装包。

## 方案 B：在苹果电脑上本地打包
如果您有苹果电脑，请按照以下步骤操作：

## 1. 准备环境
确保已安装 Python 3.9+ 和必要的依赖：

```bash
pip install -r requirements.txt
pip install pyinstaller dmgbuild
```

## 2. 使用 PyInstaller 生成 .app
在项目根目录下运行：

```bash
pyinstaller PolarBear_mac.spec
```

这将在 `dist/` 目录下生成 `PolarBear.app`。

## 3. (可选) 生成 .dmg 安装包
如果您想生成一个标准的 `.dmg` 文件，可以使用 `dmgbuild`：

```bash
# 首先安装 dmgbuild (如果还没安装)
pip install dmgbuild

# 运行打包脚本 (需要先准备 settings.json，或者直接右键 app 制作)
# 或者简单的做法：
hdiutil create -volname "PolarBear" -srcfolder dist/PolarBear.app -ov -format UDZO PolarBear_Installer.dmg
```

## 注意事项
- **OCP/OCC 依赖**：在 Mac 上，请确保通过 `conda` 或 `pip` 正确安装了 `cadquery-ocp` 或 `pythonocc-core`。
- **权限**：第一次运行生成的 `.app` 时，可能需要进入“系统设置 -> 隐私与安全性”允许运行。
