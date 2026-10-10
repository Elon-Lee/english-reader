#!/usr/bin/env python3
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class MembershipPresentationTests(unittest.TestCase):
    def setUp(self):
        self.html=(ROOT/"reader/index.html").read_text()
        self.script=(ROOT/"reader/app.js").read_text()
        self.styles=(ROOT/"reader/styles.css").read_text()

    def test_auth_and_membership_surfaces_exist(self):
        for value in ('id="saasAuth"','id="saasLoginForm"','id="saasRegisterForm"','id="membership"','id="membershipUsage"','id="membershipOrderList"','id="membershipNav"'):
            self.assertIn(value,self.html)
        self.assertIn('.membership-usage',self.styles)
        self.assertIn('.saas-auth',self.styles)

    def test_membership_reads_only_saas_endpoints(self):
        for endpoint in ('"/api/health"','"/api/auth/me"','"/api/membership/usage"','"/api/membership/orders"','"/api/auth/login"','"/api/auth/register"','"/api/auth/logout"'):
            self.assertIn(endpoint,self.script)
        self.assertIn('saas_content_migration_pending', (ROOT/"tools/reader_server.py").read_text())

    def test_catalog_and_unlocked_text_reader_surfaces_exist(self):
        for value in ('id="catalog"','id="my-library"','id="catalog-reader"','id="catalogSearchForm"','id="catalogBookList"','id="catalogDetail"','id="catalogReaderContent"'):
            self.assertIn(value,self.html)
        for endpoint in ('/api/catalog?','"/api/library"','/unlock','/reader'):
            self.assertIn(endpoint,self.script)
        for value in ('.catalog-book-list','.catalog-reader-content'):
            self.assertIn(value,self.styles)

    def test_growth_reward_surface_and_activity_wiring_exist(self):
        for value in ('id="rewards"','id="rewardStatus"','id="rewardCatalogList"','id="rewardLedgerList"'):
            self.assertIn(value,self.html)
        self.assertNotIn('id="catalogCompleteBook"',self.html)
        self.assertIn('maybeCompleteOfficialReading',self.script)
        for endpoint in ('/api/rewards/status','/api/checkins','/api/rewards/redeem','/api/rewards/activity','/api/rewards/complete-book','/api/member-invites'):
            self.assertIn(endpoint,self.script)
        self.assertIn('.reward-status',self.styles)

    def test_admin_surface_is_present_and_saas_scoped(self):
        for value in ('id="admin"','id="adminNav"','id="adminDashboard"','id="adminUserList"','id="adminInvitationForm"','id="adminQuotaForm"','id="adminCatalogReviewForm"','id="adminAuditList"'):
            self.assertIn(value,self.html)
        self.assertIn('data-admin-only="true"',self.html)
        for endpoint in ('/api/admin/dashboard','/api/admin/invitations','/api/admin/quotas/adjust','/api/admin/catalog/books','/api/admin/exports/summary'):
            self.assertIn(endpoint,self.script)
        self.assertIn('.admin-dashboard',self.styles)

    def test_phase6_account_media_and_legal_surfaces_exist(self):
        for value in ('id="accountExport"','id="accountDelete"','id="accountCancelDeletion"','id="adminMediaList"','href="/terms"','href="/privacy"'):
            self.assertIn(value,self.html)
        for endpoint in ('/api/account/export','/api/account/deletion','/api/account/deletion/cancel','/api/admin/media-assets'):
            self.assertIn(endpoint,self.script)
        self.assertIn('.account-lifecycle',self.styles)
        for page in ('terms.html','privacy.html','content-policy.html','refunds.html','copyright.html'):
            self.assertTrue((ROOT/'reader'/'legal'/page).is_file())

    def test_private_workspace_surface_and_routes_exist(self):
        for value in ('id="workspaceNav"','id="workspace"','id="workspaceBookList"','id="workspace-reader"','id="workspaceReaderContent"','id="workspaceWordPanel"','data-screen="stats" data-saas-only="true"','data-screen="vocab" data-saas-only="true"'):
            self.assertIn(value,self.html)
        for endpoint in ('/api/workspace/books','/api/workspace/activity','/api/workspace/vocabulary','/api/workspace/learning-days'):
            self.assertIn(endpoint,self.script)
        self.assertIn('.workspace-book-card',self.styles)
        self.assertIn('.workspace-reader-word',self.styles)
        self.assertIn('saveWorkspaceVocabulary',self.script)
        self.assertIn('saveWorkspaceAnnotation',self.script)
        self.assertIn('loadWorkspaceWordContext',self.script)
        self.assertIn('loadWorkspaceGrammar',self.script)
        self.assertIn('/api/word-context',self.script)
        self.assertIn('/api/sentence-grammar',self.script)
        self.assertIn('openSaasFullReader',self.script)
        self.assertIn('id="player"',self.html)

    def test_native_text_import_surface_and_task_routes_exist(self):
        for value in ('id="workspaceTextImportForm"','id="workspaceTextImportFile"','id="workspaceYoutubeImportForm"','id="workspaceYoutubeImportUrl"','id="workspaceTaskList"','id="workspaceTaskRefresh"'):
            self.assertIn(value,self.html)
        for endpoint in ('/api/workspace/imports','/upload','/complete','/cancel'):
            self.assertIn(endpoint,self.script)
        self.assertIn('.workspace-import-form',self.styles)
        self.assertIn('application/pdf',self.html)
        self.assertIn('audio/mpeg',self.html)
        self.assertIn('video/mp4',self.html)
        self.assertIn('startWorkspaceYoutubeImport',self.script)

    def test_saas_navigation_modals_and_admin_tabs_exist(self):
        for value in ('id="catalogDetailDialog"','id="adminTabs"','data-admin-tab="overview"','data-admin-tab="media"','id="adminMediaPrev"','id="adminMediaNext"'):
            self.assertIn(value,self.html)
        for value in ('history[method]','setAdminTab','setSettingsTab','popstate','maybeCompleteOfficialReading'):
            self.assertIn(value,self.script)

if __name__=="__main__":unittest.main()
