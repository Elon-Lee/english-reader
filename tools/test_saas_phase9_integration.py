#!/usr/bin/env python3
"""Acceptance tests for tenant-scoped cached AI generation and quotas."""
from __future__ import annotations

import json
import os
import unittest
from datetime import timedelta
from urllib.parse import urlsplit

from saas_ai import WorkspaceAIService
from saas_auth import SaaSError, SaaSService, new_id, token_hash, utcnow
from saas_membership import MembershipService


TEST_URL=os.environ.get("SHIYUE_SAAS_TEST_DATABASE_URL","")


def assert_safe_database(url:str)->None:
    if not urlsplit(url).path.rsplit("/",1)[-1].endswith("_test"):raise RuntimeError("SHIYUE_SAAS_TEST_DATABASE_URL 必须指向名称以 _test 结尾的专用数据库。")


class WorkspaceAITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert_safe_database(TEST_URL);cls.environment={"DATABASE_URL":TEST_URL,"SHIYUE_SAAS_ENABLED":"1","SESSION_SECRET":"test-only-session-secret-that-is-at-least-32-characters","BOOTSTRAP_ADMIN_EMAIL":"admin@local.test","BOOTSTRAP_ADMIN_PASSWORD":"phase9 admin password"}
        cls.accounts=SaaSService(TEST_URL,cls.environment);cls.accounts.migrate();cls.memberships=MembershipService(cls.accounts)

    def setUp(self):
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""TRUNCATE TABLE workspace_ai_results,workspace_import_tasks,workspace_activity_events,workspace_progress,workspace_settings,security_events,account_deletion_requests,asset_usage,asset_variants,media_assets,admin_audit_logs,platform_settings,
                member_invite_rewards,member_invites,member_invite_allowances,reward_activity_events,reward_daily_activity,reward_redemptions,reward_ledger,checkins,
                official_book_unlocks,user_library,catalog_book_tags,catalog_books,catalog_tags,catalog_series,membership_audit,usage_ledger,quota_reservations,usage_periods,subscriptions,manual_orders,assets,
                content_sentence_grammar,content_learning_daily,content_word_annotations,content_vocabulary,content_books,invitation_uses,invitations,password_reset_tokens,email_verifications,user_sessions,devices,user_roles,users,roles RESTART IDENTITY CASCADE""")
        self.admin=self.accounts.bootstrap_admin();invitation=self.accounts.create_invitation("AI-TEST",max_uses=10,created_by=str(self.admin["id"]));self.owner=self.accounts.register("ai-owner@local.test","ai owner password",invitation["code"])["user"];self.other=self.accounts.register("ai-other@local.test","ai other password",invitation["code"])["user"];self.verify(str(self.owner["id"]));self.verify(str(self.other["id"]));self.book_id=self.create_book(str(self.owner["id"]));self.calls=[]

        def generator(kind,prompt):
            self.calls.append((kind,prompt));return {"text":"语境讲解" if kind=="word_context" else "句法讲解","provider":"fake-ai"}
        self.ai=WorkspaceAIService(self.accounts,self.memberships,generator)

    def verify(self,user_id:str)->None:
        raw="verify-"+new_id()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:cursor.execute("INSERT INTO email_verifications(id,user_id,token_hash,expires_at) VALUES(%s,%s,%s,%s)",(new_id(),user_id,token_hash(raw),utcnow()+timedelta(days=1)))
        self.accounts.verify_email(raw)

    def create_book(self,owner_id:str)->str:
        book_id="private-ai-book";data={"id":book_id,"title":"AI Private","sentences":[{"id":"s1","text":"We survive together.","words":[{"text":"We"},{"text":"survive"},{"text":"together"}]},{"id":"s2","text":"This is the next sentence.","words":[]}]}
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""INSERT INTO content_books(id,owner_id,title,english_title,series,level,source_type,source_path,status,visibility,cover_url,page_base_url,audio_url,pdf_url,video_url,duration,alignment,data_json,quality_json,created_at,updated_at)
                VALUES(%s,%s,'AI Private','AI Private','Private','1','text','private/ai','ready','private','','','','','',0,'',%s::jsonb,'{}'::jsonb,NOW(),NOW())""",(book_id,owner_id,json.dumps(data)))
                cursor.execute("INSERT INTO content_sentence_grammar(book_id,sentence_id,payload) VALUES(%s,'s1','{\"pattern\":\"SVO\"}'::jsonb)",(book_id,))
        return book_id

    def test_context_and_grammar_charge_once_then_use_owner_cache(self):
        owner,other=str(self.owner["id"]),str(self.other["id"])
        first=self.ai.context(owner,self.book_id,"s1",1);second=self.ai.context(owner,self.book_id,"s1",1)
        self.assertTrue(first["charged"]);self.assertFalse(first["cached"]);self.assertTrue(second["cached"]);self.assertFalse(second["charged"]);self.assertEqual(first["word"],"survive")
        grammar=self.ai.grammar(owner,self.book_id,"s1");cached=self.ai.grammar(owner,self.book_id,"s1")
        self.assertTrue(grammar["charged"]);self.assertEqual(grammar["structure"]["pattern"],"SVO");self.assertTrue(cached["cached"]);self.assertEqual(len(self.calls),2)
        usage=self.memberships.usage(owner);context_usage=next(row for row in usage["usage"] if row["feature"]=="ai_context_generations");grammar_usage=next(row for row in usage["usage"] if row["feature"]=="ai_grammar_generations")
        self.assertEqual(context_usage["used"],1);self.assertEqual(context_usage["reserved"],0);self.assertEqual(grammar_usage["used"],1);self.assertEqual(grammar_usage["reserved"],0)
        with self.assertRaises(SaaSError) as denied:self.ai.context(other,self.book_id,"s1",1)
        self.assertEqual(denied.exception.code,"workspace_book_not_found")

    def test_failed_generation_releases_quota_and_can_retry(self):
        owner=str(self.owner["id"]);attempts=[]
        def flaky(kind,prompt):
            attempts.append(kind)
            if len(attempts)==1:raise RuntimeError("simulated provider failure")
            return {"text":"重试成功","provider":"fake-ai"}
        ai=WorkspaceAIService(self.accounts,self.memberships,flaky)
        with self.assertRaises(SaaSError) as failed:ai.context(owner,self.book_id,"s1",0)
        self.assertEqual(failed.exception.code,"ai_generation_failed")
        usage=self.memberships.usage(owner);context_usage=next(row for row in usage["usage"] if row["feature"]=="ai_context_generations");self.assertEqual(context_usage["used"],0);self.assertEqual(context_usage["reserved"],0)
        retried=ai.context(owner,self.book_id,"s1",0);self.assertTrue(retried["charged"]);self.assertEqual(retried["explanation"],"重试成功")
        usage=self.memberships.usage(owner);context_usage=next(row for row in usage["usage"] if row["feature"]=="ai_context_generations");self.assertEqual(context_usage["used"],1);self.assertEqual(context_usage["reserved"],0)


if __name__=="__main__":unittest.main()
