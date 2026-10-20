# 品牌图标交接

## 目标

交付拾页网站的 320×320 像素图标文件。

## 已完成

- 2026-10-20：沿用现有 `reader/favicon.svg` 的深绿圆角底、米白书页和暖橙点缀，提供透明边角 PNG 与明确 320×320 尺寸的 SVG 源文件。
- 交付位于 `output/branding/`，独立导出，不替换当前站点图标引用。
- 已检查成品图像，PNG 为 320×320 RGBA；构建、modern smoke、22 项 UI 测试、JS 检查、Python 编译及 `git diff --check` 均通过。

## 未完成

- 无；若后续要求替换网站图标，再接入前端入口和部署资源。

## 关键文件

- `reader/favicon.svg`：原品牌矢量图形。
- `output/branding/shiyue-icon-320.svg`：320×320 矢量源文件。
- `output/branding/shiyue-icon-320.png`：320×320 RGBA PNG 成品。

## 验收重点

- 检查 PNG 格式、320×320 尺寸、透明边角和完整图形；与原 favicon 一致。
- 使用工作区运行时的 `sharp` 从 SVG 按 4 倍分辨率栅格化，缩小至 320×320 并导出 PNG。
- 常规验证：`npm run build:modern`、`npm run test:modern`、`npm run test:ui`、`npm run check:js`、`python3 -m py_compile tools/reader_server.py`、`git diff --check`。
