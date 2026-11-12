"""SMTP transport contracts; no real mail is sent."""
import smtplib
import ssl
import unittest
from unittest.mock import patch

from saas_auth import SaaSService


class MailTests(unittest.TestCase):
    def test_site_specific_links_use_trusted_config(self):
        from saas_sites import site_context
        service = SaaSService(environment={
            'APP_BASE_URL': 'https://fallback.example',
            'CN_APP_BASE_URL': 'https://learn.cn.example',
            'INTL_APP_BASE_URL': 'https://intl.example',
        })
        with site_context('intl'):
            self.assertEqual(service._app_url('/reset-password?token=safe'), 'https://intl.example/reset-password?token=safe')
        self.assertEqual(service._app_url('/verify-email?token=safe'), 'https://learn.cn.example/verify-email?token=safe')

    def service(self, port):
        return SaaSService(environment={
            "SMTP_HOST": "smtpdm.aliyun.com", "SMTP_PORT": str(port),
            "SMTP_USER": "noreply@example.test", "SMTP_FROM": "noreply@example.test",
            "SMTP_PASSWORD": "test-only", "SMTP_FROM_NAME": "纸间微光",
        })

    @patch("saas_auth.smtplib.SMTP_SSL")
    @patch("saas_auth.smtplib.SMTP")
    def test_465_uses_verified_implicit_tls_and_envelope_sender(self, plain, secure):
        self.assertTrue(self.service(465)._send_mail("to@example.test", "验证", "正文"))
        plain.assert_not_called()
        context = secure.call_args.kwargs["context"]
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        client = secure.return_value.__enter__.return_value
        client.starttls.assert_not_called()
        client.login.assert_called_once_with("noreply@example.test", "test-only")
        call = client.send_message.call_args
        self.assertEqual(call.kwargs["from_addr"], "noreply@example.test")
        self.assertIn("纸间微光", str(call.args[0]["From"]))

    @patch("saas_auth.smtplib.SMTP")
    def test_587_requires_verified_starttls(self, smtp):
        self.assertTrue(self.service(587)._send_mail("to@example.test", "subject", "body"))
        client = smtp.return_value.__enter__.return_value
        self.assertEqual(client.starttls.call_args.kwargs["context"].verify_mode, ssl.CERT_REQUIRED)

    @patch("saas_auth.smtplib.SMTP_SSL", side_effect=smtplib.SMTPAuthenticationError(535, b"denied"))
    def test_failure_is_false(self, _):
        self.assertFalse(self.service(465)._send_mail("to@example.test", "subject", "body"))

    def test_auth_mail_brand_and_original_token_links(self):
        service = SaaSService(environment={"APP_BASE_URL": "https://rynenglish.com"})
        for method, path, subject in (
            (service._send_verification, '/verify-email', '验证你的 纸间微光 邮箱'),
            (service._send_password_reset, '/reset-password', '重置 纸间微光 密码'),
        ):
            with self.subTest(path=path), patch.object(service, '_send_mail', return_value=True) as send:
                self.assertTrue(method('to@example.test', 'test token+/'))
                email, title, body = send.call_args.args
                self.assertEqual(email, 'to@example.test')
                self.assertEqual(title, subject)
                self.assertIn(f'https://rynenglish.com{path}?token=test%20token%2B/', body)
                self.assertIn('纸间微光\n一页一光，静读慢行。', body)
                self.assertNotIn('拾页', body)


if __name__ == "__main__":
    unittest.main()
