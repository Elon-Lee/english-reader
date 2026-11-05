"""Opt-in real Chrome + SDK + Python + Java + isolated PostgreSQL/Redis test.

Requires playwright, Pillow and numpy in the test environment only.
Build the frontend into .local/captcha-fix-build and start the test Java service.
"""
import base64
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


@unittest.skipUnless(os.environ.get("SHIYUE_CAPTCHA_BROWSER_TEST") == "1", "Opt-in isolated browser test")
class AuthCaptchaBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from saas_auth import SaaSService
        from saas_cache import SaaSCache
        from saas_captcha import CaptchaService
        from playwright.sync_api import sync_playwright

        cls.root = Path(__file__).resolve().parents[1]
        database = os.environ["SHIYUE_SAAS_TEST_DATABASE_URL"]
        assert database.rsplit("/", 1)[-1].endswith("_test"), "Disposable database required"
        cls.environment = {**os.environ, "DATABASE_URL": database,
            "REDIS_URL": os.environ["SHIYUE_CAPTCHA_TEST_REDIS_URL"],
            "SHIYUE_SAAS_ENABLED": "1", "SHIYUE_RUNTIME_MODE": "saas", "SHIYUE_DEPLOYMENT_MODE": "remote",
            "SESSION_SECRET": "test-only-captcha-browser-session-secret-at-least-32",
            "BOOTSTRAP_ADMIN_EMAIL": "captcha-browser@example.test", "BOOTSTRAP_ADMIN_PASSWORD": "browser test password",
            "SHIYUE_CAPTCHA_SECRET": "test-only-captcha-internal-secret-at-least-32",
            "APP_BASE_URL": "http://127.0.0.1:4185", "SMTP_HOST": "", "SMTP_FROM": "",
            "READER_HOST": "127.0.0.1", "READER_PORT": "8895", "PYTHONDONTWRITEBYTECODE": "1"}
        accounts = SaaSService(database, cls.environment)
        accounts.migrate()
        admin = accounts.bootstrap_admin()
        cls.cache = SaaSCache(cls.environment["REDIS_URL"]).client
        CaptchaService(accounts, cls.cache, cls.environment).update_config(str(admin["id"]), {"captchaEnabled": True})
        cls.logs = []
        cls.processes = []
        for name, module, extra in (("backend", "reader_server.py", {}), ("frontend", "saas_frontend_server.py", {
                "FRONTEND_ROOT": str(cls.root / ".local/captcha-fix-build"), "FRONTEND_HOST": "127.0.0.1",
                "FRONTEND_PORT": "4185", "SAAS_BACKEND_URL": "http://127.0.0.1:8895"})):
            log = (cls.root / f".local/captcha-browser-{name}.log").open("w")
            cls.logs.append(log)
            cls.processes.append(subprocess.Popen([sys.executable, str(cls.root / "tools" / module)],
                cwd=cls.root, env={**cls.environment, **extra}, stdout=log, stderr=log))
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True,
            executable_path=os.environ.get("SHIYUE_TEST_CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        for process in cls.processes:
            process.terminate()
            process.wait(timeout=10)
        for log in cls.logs:
            log.close()
        cls.cache.close()

    def solve_test_photo(self, challenge):
        # Test fixture only: compare the known bundled photo with its rotated crop.
        # No server answers or production-only bypass endpoints are exposed.
        import numpy as np
        from PIL import Image
        template = Image.open(io.BytesIO(base64.b64decode(challenge["templateImage"].split(",")[1]))).convert("RGBA")
        original = Image.open(self.root / "services/captcha/src/main/resources/captcha/animal-default.jpg").convert("RGB")
        width, height = template.size
        left = (original.width - width) // 2
        top = (original.height - height) // 2
        target = np.asarray(original.crop((left, top, left + width, top + height)), dtype=float)
        y, x = np.ogrid[:height, :width]
        mask = (x - width / 2) ** 2 + (y - height / 2) ** 2 < (width * .38) ** 2
        def score(degree):
            rotated = np.asarray(template.rotate(-degree, resample=Image.Resampling.BILINEAR), dtype=float)[:, :, :3]
            return float(np.mean((rotated[mask] - target[mask]) ** 2))
        return min(range(360), key=score)

    def drag(self, page, angle):
        box = page.locator("#tianai-captcha-slider-move-btn").bounding_box()
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        page.mouse.move(x, y)
        page.mouse.down()
        for i in range(1, 41):
            progress = 1 - (1 - i / 40) ** 3
            page.mouse.move(x + angle / 360 * 242 * progress, y + i % 3)
            page.wait_for_timeout(8 + i * 2)
        page.mouse.up()

    def test_single_centered_panel_and_real_sdk_flows(self):
        from playwright.sync_api import expect
        context = self.browser.new_context(viewport={"width": 1200, "height": 800})
        self.addCleanup(context.close)
        page = context.new_page()
        self.addCleanup(lambda: page.screenshot(path=str(self.root / ".local/captcha-browser-last.png")))
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        for mode in ("forgot", "register", "login"):
            page.goto("http://127.0.0.1:4185/" + ("register" if mode == "register" else "login"))
            if mode == "forgot":
                page.get_by_text("找回密码", exact=True).click()
            page.get_by_label("邮箱", exact=True).fill("captcha-browser@example.test" if mode == "login" else "captcha-nonexistent@example.test")
            if mode != "forgot":
                page.get_by_label("密码", exact=True).fill("browser test password")
            if mode == "register":
                page.get_by_label("邀请码", exact=True).fill("deliberately-invalid-code")
            submit = page.locator('form button[type="submit"]')
            with page.expect_response("**/api/auth/captcha/gen") as generated:
                submit.click()
            challenge = generated.value.json()["data"]
            expect(page.locator("#tianai-captcha-slider-bg-img")).to_be_visible()
            expect(page.locator(".auth-captcha-status")).to_have_count(0)
            expect(page.locator(".ant-modal-wrap")).to_have_count(0)
            expect(page.locator("#tianai-captcha-parent")).to_have_count(1)
            for viewport in ({"width": 1200, "height": 800}, {"width": 671, "height": 716}):
                page.set_viewport_size(viewport)
                box = page.locator("#tianai-captcha-parent").bounding_box()
                self.assertLess(abs(box["x"] + box["width"] / 2 - viewport["width"] / 2), 2)
                self.assertLess(abs(box["y"] + box["height"] / 2 - viewport["height"] / 2), 2)
            page.wait_for_timeout(750)
            if mode == "forgot":
                page.screenshot(path=str(self.root / ".local/captcha-browser-centered.png"))
            if mode == "forgot":
                with page.expect_response("**/api/auth/captcha/gen") as refreshed:
                    with page.expect_response("**/api/auth/captcha/check") as rejected:
                        self.drag(page, 5)
                    self.assertNotEqual(rejected.value.json().get("code"), 200)
                challenge = refreshed.value.json()["data"]
                page.wait_for_timeout(550)
            angle = self.solve_test_photo(challenge)
            endpoint = {"forgot": "forgot-password", "register": "register", "login": "login"}[mode]
            with page.expect_response("**/api/auth/" + endpoint) as business:
                with page.expect_response("**/api/auth/captcha/check") as checked:
                    self.drag(page, angle)
                result = checked.value.json()
                self.assertEqual(result.get("code"), 200, result)
                self.assertTrue(result["data"]["captchaToken"])
            payload = business.value.json()
            self.assertNotEqual(payload.get("code"), "captcha_required", payload)
            self.assertEqual(business.value.status, 400 if mode == "register" else 200, payload)
            expect(page.locator(".auth-captcha-dialog")).to_have_count(0)
            self.assertTrue(json.loads(business.value.request.post_data)["captchaToken"])
            if mode == "login":
                expect(page).to_have_url("http://127.0.0.1:4185/app")
        self.assertFalse(errors, errors)


if __name__ == "__main__":
    unittest.main()
