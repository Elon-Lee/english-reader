#!/usr/bin/env python3
"""Guard the invitation-only frontend against commercial feature reintroduction."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'frontend' / 'src'


class PrivateFrontendTests(unittest.TestCase):
    def test_no_commercial_api_or_navigation_remains(self):
        for path in SOURCE.rglob('*'):
            if path.suffix not in {'.jsx', '.js', '.mjs', '.css'} or '.test.' in path.name:
                continue
            text = path.read_text()
            self.assertIsNone(re.search(r'/api/(?:admin/)?(?:membership|commerce|billing|payments|payment-config|payment-orders|subscriptions|manual-orders)\b', text), str(path))
            self.assertNotIn('screen=membership', text, str(path))
            self.assertNotIn('付费会员', text, str(path))
            self.assertNotIn('canWatchHdVideo', text, str(path))

    def test_invitation_is_required(self):
        text = (SOURCE / 'main.jsx').read_text()
        self.assertRegex(text, r'name="invitationCode"[^\n]*required: true')
        self.assertIn('受邀注册', text)

    def test_removed_pages_have_no_modules(self):
        for name in ['pages/MembershipPage.jsx', 'components/CommerceAdmin.jsx',
                     'components/PaymentOperations.jsx', 'components/RedemptionAdmin.jsx',
                     'components/MembershipLimitModal.jsx', 'api/membershipLimit.js',
                     'hooks/usePurchasePreviews.js']:
            self.assertFalse((SOURCE / name).exists(), name)


if __name__ == '__main__':
    unittest.main()
