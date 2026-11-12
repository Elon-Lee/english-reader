"""Verify each production dependency graph keeps the site boundary intact."""
from pathlib import Path
import json
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'frontend/src'


def dependencies(site):
    pending = [SOURCE / 'main.jsx']
    visited = set()
    while pending:
        path = pending.pop().resolve()
        if path in visited:
            continue
        visited.add(path)
        text = path.read_text()
        for name in re.findall(r'(?:from\s*|import\s*\(?\s*)[\'\"]([^\'\"]+)[\'\"]', text):
            if name == '@site':
                target = SOURCE / 'sites' / site / 'index.jsx'
            elif name.startswith('.'):
                target = path.parent / name.split('?')[0]
                if not target.suffix:
                    target = next((target.with_suffix(ext) for ext in ('.jsx', '.js', '.mjs', '.css') if target.with_suffix(ext).exists()), target)
            else:
                continue
            if target.is_file() and target.suffix in {'.jsx', '.js', '.mjs', '.css'}:
                pending.append(target)
    return visited


class DualEntryFrontendTests(unittest.TestCase):
    def test_domestic_graph_excludes_international_commerce(self):
        graph = dependencies('cn')
        self.assertTrue(any('/sites/cn/' in str(path) for path in graph))
        self.assertFalse(any('/sites/intl/' in str(path) for path in graph))
        for path in graph:
            self.assertIsNone(re.search(r'/api/(?:admin/)?(?:membership|commerce|payments|payment-config|payment-orders)\b', path.read_text()), str(path))

    def test_international_graph_restores_real_commerce_and_shared_reader(self):
        graph = dependencies('intl')
        text = '\n'.join(path.read_text() for path in graph)
        for endpoint in ('/api/commerce/products', '/api/membership/usage', '/api/membership/orders', '/api/payments/alipay/orders'):
            self.assertTrue(endpoint in text, f'missing international API: {endpoint}')
        self.assertIn(SOURCE / 'pages/ReaderPage.jsx', graph)
        self.assertIn(SOURCE / 'components/AuthCaptcha.jsx', graph)
        self.assertNotIn('speechSynthesis', text)

    def test_two_builds_have_distinct_output_and_public_assets(self):
        package = json.loads((ROOT / 'package.json').read_text())
        self.assertIn('build:intl', package['scripts'])
        self.assertIn('build:sites', package['scripts'])
        config = (ROOT / 'frontend/vite.config.js').read_text()
        self.assertIn('site-intl', config)
        self.assertIn('public-intl', config)
        self.assertIn('@site', config)
        self.assertFalse(any(path.is_file() for path in (ROOT / 'frontend/public/product').rglob('*')))
        self.assertTrue((ROOT / 'frontend/public-intl/product/reader-lookup-20261026.webp').is_file())

    def test_payment_ui_never_offers_simulated_success(self):
        payment = (SOURCE / 'sites/intl/pages/PublicSite.jsx').read_text()
        self.assertNotIn('simulate-paid', payment)
        self.assertNotIn('RYNENGLISH_LOCAL_TEST_PAYMENT:', payment)
        self.assertIn('alipayOrder.qrCode && !alipayOrder.testMode', payment)

    def test_old_commercial_forms_report_pending_saves(self):
        for file in ['CommerceAdmin.jsx', 'BenefitAdmin.jsx']:
            text = (SOURCE / 'sites/intl/components' / file).read_text()
            self.assertIn('setSaving(true)', text, file)
            self.assertIn('loading={saving}', text, file)


if __name__ == '__main__':
    unittest.main()
