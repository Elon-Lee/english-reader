"""SMTP transport contracts; no real mail is sent."""
import smtplib
import ssl
import unittest
from unittest.mock import patch

from saas_auth import SaaSService


class MailTests(unittest.TestCase):
    def service(self, port):
        return SaaSService(environment={
            "SMTP_HOST": "smtpdm.aliyun.com", "SMTP_PORT": str(port),
            "SMTP_USER": "noreply@example.test", "SMTP_FROM": "noreply@example.test",
            "SMTP_PASSWORD": "test-only", "SMTP_FROM_NAME": "RynEnglish",
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
        self.assertIn("RynEnglish", str(call.args[0]["From"]))

    @patch("saas_auth.smtplib.SMTP")
    def test_587_requires_verified_starttls(self, smtp):
        self.assertTrue(self.service(587)._send_mail("to@example.test", "subject", "body"))
        client = smtp.return_value.__enter__.return_value
        self.assertEqual(client.starttls.call_args.kwargs["context"].verify_mode, ssl.CERT_REQUIRED)

    @patch("saas_auth.smtplib.SMTP_SSL", side_effect=smtplib.SMTPAuthenticationError(535, b"denied"))
    def test_failure_is_false(self, _):
        self.assertFalse(self.service(465)._send_mail("to@example.test", "subject", "body"))


if __name__ == "__main__":
    unittest.main()
