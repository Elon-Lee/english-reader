"""Smoke checks against both built artifacts, including public resource isolation."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BuiltSiteTests(unittest.TestCase):
    def test_domestic_artifact_has_no_commercial_code_or_marketing_assets(self):
        site = ROOT / 'reader/site'
        code = '\n'.join(path.read_text() for path in (site / 'assets').glob('*.js'))
        for marker in ['/api/commerce/', '/api/membership/', '/api/payments/', '云猫', '支付宝', '会员中心']:
            self.assertFalse(marker in code, f'domestic bundle leaked {marker}')
        self.assertFalse((site / 'assets/payment-alipay.svg').exists())
        self.assertFalse((site / 'product/reader-lookup-20261026.webp').exists())

    def test_international_artifact_has_commerce_metadata_and_original_assets(self):
        site = ROOT / 'reader/site-intl'
        html = (site / 'index.html').read_text()
        self.assertIn('<title>RynEnglish</title>', html)
        self.assertIn('https://10ye.cc/', html)
        code = '\n'.join(path.read_text() for path in (site / 'assets').glob('*.js'))
        for marker in ['/api/commerce/products', '/api/membership/usage', '/api/payments/alipay/orders', '会员中心']:
            self.assertTrue(marker in code, f'international bundle missing {marker}')
        for name in ['product/reader-lookup-20261026.webp', 'assets/payment-alipay.svg', 'brand/rynenglish-mark.svg']:
            self.assertEqual((site / name).read_bytes(), (ROOT / 'frontend/public-intl' / name).read_bytes())
        self.assertTrue((site / 'tianai/js/tac.min.js').is_file())


if __name__ == '__main__':
    unittest.main()
