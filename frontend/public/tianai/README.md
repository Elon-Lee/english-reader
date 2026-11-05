# Tianai browser SDK

Self hosted official Tianai 1.5.6 assets, downloaded on 2026-11-05.

- Release: https://gitee.com/dromara/tianai-captcha/releases/download/tianai-captcha-1.5.6/tac-web.zip
- Release SHA-256: `354c1d492c97a0a4c3956d7f762d1e903cc5a90f837afb365542112491b01adf`
- Loader: https://minio.tianai.cloud/public/static/captcha/js/load.min.js
- Loader SHA-256: `a241bbc17bf06a579b05e2a4759e9f135ebf8521a738a27d1ef9db906b4291a9`
- Upstream source: https://github.com/dromara/tianai-captcha (`89c064a29abd76bf0b253adbe7f31e8baf965e84`, version 1.5.6).
- License is included as `LICENSE` (MulanPSL-2.0).

The loader is named `load.js`; `window.loadTAC('/tianai', config, style)` loads only local JS/CSS. One upstream CSS relative image URL was changed from `../../tac/images/dun.jpeg` to `../images/dun.jpeg` to support this `/tianai` mount. No other SDK behavior was changed. Bundled UI images are local/base64; generated captcha images come from the backend as data URLs.
