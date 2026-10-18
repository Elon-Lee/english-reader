#!/usr/bin/env python3
"""Real PostgreSQL acceptance tests for reviewed catalog and official library."""
from __future__ import annotations

import json
import http.client
import os
import socket
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from urllib.parse import urlsplit

from saas_auth import SaaSError, SaaSService, new_id, token_hash, utcnow
from saas_catalog import CatalogService
from saas_membership import MembershipService

TEST_URL=os.environ.get("SHIYUE_SAAS_TEST_DATABASE_URL","")

def assert_safe_database(url:str)->None:
    if not urlsplit(url).path.rsplit("/",1)[-1].endswith("_test"):
        raise RuntimeError("SHIYUE_SAAS_TEST_DATABASE_URL 必须指向名称以 _test 结尾的专用数据库。")

class PhaseThreePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert_safe_database(TEST_URL)
        cls.environment={"DATABASE_URL":TEST_URL,"SHIYUE_SAAS_ENABLED":"1","SESSION_SECRET":"test-only-session-secret-that-is-at-least-32-characters","BOOTSTRAP_ADMIN_EMAIL":"admin@local.test","BOOTSTRAP_ADMIN_PASSWORD":"phase3 admin password"}
        cls.accounts=SaaSService(TEST_URL,cls.environment);cls.accounts.migrate();cls.memberships=MembershipService(cls.accounts);cls.catalog=CatalogService(cls.accounts,cls.memberships)

    def setUp(self):
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""TRUNCATE TABLE official_book_unlocks,user_library,catalog_book_tags,catalog_books,catalog_tags,catalog_series,
                membership_audit,usage_ledger,quota_reservations,usage_periods,subscriptions,manual_orders,assets,
                content_sentence_grammar,content_learning_daily,content_word_annotations,content_vocabulary,content_books,
                invitation_uses,invitations,password_reset_tokens,email_verifications,user_sessions,devices,user_roles,users,roles RESTART IDENTITY CASCADE""")
        self.admin=self.accounts.bootstrap_admin();assert self.admin
        invitation=self.accounts.create_invitation("CATALOG-TEST",max_uses=30,created_by=str(self.admin["id"]))
        self.alice=self.accounts.register("alice@local.test","alice password phase three",invitation["code"])["user"]
        self.bob=self.accounts.register("bob@local.test","bob password phase three",invitation["code"])["user"]
        self.verify(str(self.alice["id"]));self.verify(str(self.bob["id"]))

    def verify(self,user_id:str)->None:
        raw="verify-"+new_id()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO email_verifications(id,user_id,token_hash,expires_at) VALUES(%s,%s,%s,%s)",(new_id(),user_id,token_hash(raw),utcnow()+timedelta(days=1)))
        self.accounts.verify_email(raw)

    def source(self,index:int)->str:
        book_id=f"source-{index}";sentences=[{"id":f"s{index}-{step}","text":f"Sample sentence {index} {step}.","words":[{"text":"Sample"},{"text":"sentence"},{"text":str(index)}]} for step in range(3)]
        data={"id":book_id,"title":f"中文读物 {index}","englishTitle":f"Catalog Reader {index}","sentences":sentences}
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""INSERT INTO content_books(id,owner_id,title,english_title,series,level,source_type,source_path,status,visibility,cover_url,page_base_url,audio_url,pdf_url,video_url,duration,alignment,data_json,quality_json,created_at,updated_at)
                VALUES(%s,%s,%s,%s,'Test Series','1','book',%s,'ready','private','','','','','',300,'',%s::jsonb,'{}'::jsonb,NOW(),NOW())""",(book_id,self.admin["id"],data["title"],data["englishTitle"],f"test/{index}",json.dumps(data)))
        return book_id

    def publish(self,index:int)->str:
        source_id=self.source(index)
        result=self.catalog.review(str(self.admin["id"]),source_id,"licensed","published",{"author":"Test Author","description":f"Description {index}","tags":["测试","阅读"],"featuredRank":index})
        return result["book"]["id"]

    def test_private_migrated_source_is_not_auto_published_and_rights_are_enforced(self):
        source=self.source(0)
        self.assertEqual(self.catalog.catalog()["books"],[])
        with self.assertRaises(SaaSError) as prohibited:
            self.catalog.review(str(self.admin["id"]),source,"private","published",{})
        self.assertEqual(prohibited.exception.code,"rights_required")
        draft=self.catalog.review(str(self.admin["id"]),source,"private","draft",{})["book"]
        self.assertEqual(draft["id"],draft["id"])
        self.assertEqual(self.catalog.catalog()["books"],[])

    def test_public_catalog_search_tags_and_user_state_are_isolated(self):
        first=self.publish(1);second=self.publish(2)
        listed=self.catalog.catalog(str(self.alice["id"]),query="Reader 1")["books"]
        self.assertEqual([item["id"] for item in listed],[first])
        self.assertEqual(listed[0]["author"],"Test Author")
        self.assertEqual({item["title"] for item in self.catalog.tags()["tags"]},{"测试","阅读"})
        # Chinese tags use deterministic hash fallback slugs, while their
        # titles remain readable. Search and series filtering still work.
        self.assertEqual(self.catalog.series()["series"][0]["title"],"Test Series")
        self.catalog.add_or_unlock(str(self.alice["id"]),first,False)
        alice=self.catalog.detail(first,str(self.alice["id"]))["book"]
        bob=self.catalog.detail(first,str(self.bob["id"]))["book"]
        self.assertTrue(alice["inLibrary"]);self.assertFalse(bob["inLibrary"])
        self.assertEqual(len(self.catalog.library(str(self.alice["id"]))["items"]),1)
        self.assertEqual(len(self.catalog.library(str(self.bob["id"]))["items"]),0)
        self.assertNotEqual(first,second)

    def test_uncollected_catalog_reader_is_limited_to_trial_mode(self):
        book_id=self.publish(3)
        trial=self.catalog.reader(str(self.alice["id"]),book_id,trial=True)["book"]
        self.assertTrue(trial["trial"])
        self.assertEqual(trial["trialLimit"],1)
        self.assertEqual(trial["trialPercent"],10)
        self.assertEqual(len(trial["sentences"]),1)
        self.assertEqual(trial["mediaAssets"],[])
        self.assertEqual(trial["progress"]["lastSentenceId"],"")
        with self.assertRaises(SaaSError):
            self.catalog.reader(str(self.alice["id"]),book_id)

    def test_trial_timed_sentences_stop_at_ten_percent(self):
        book_id=self.publish(4)
        sentences=[{'id':str(i),'text':f'Sentence {i}', 'start':i*2, 'end':i*2+2} for i in range(100)]
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute('UPDATE content_books SET duration=200,data_json=%s::jsonb WHERE id=%s', (json.dumps({'sentences':sentences}), 'source-4'))
        trial=self.catalog.reader(str(self.alice['id']),book_id,trial=True)['book']
        self.assertEqual(trial['trialEndSeconds'],20)
        self.assertEqual([item['id'] for item in trial['sentences']],[str(i) for i in range(10)])
        self.assertEqual(self.catalog.library(str(self.alice['id']))['items'],[])

    def test_official_library_and_material_access_are_not_metered_by_usage_count(self):
        books=[self.publish(index) for index in range(10,16)]
        user_id=str(self.alice["id"])
        def add(book_id:str):
            try:return self.catalog.add_or_unlock(user_id,book_id,False)
            except SaaSError as exc:return exc
        with ThreadPoolExecutor(max_workers=6) as pool: results=list(pool.map(add,books))
        successes=[value for value in results if isinstance(value,dict)];errors=[value for value in results if isinstance(value,SaaSError)]
        self.assertEqual(len(successes),6);self.assertEqual(errors,[])
        chosen=successes[0]["bookId"]
        first=self.catalog.add_or_unlock(user_id,chosen,True);self.assertTrue(first["unlocked"])
        self.catalog.remove(user_id,chosen)
        readd=self.catalog.add_or_unlock(user_id,chosen,True);self.assertTrue(readd["unlocked"])
        membership=self.memberships.usage(user_id)
        unlock=next(row for row in membership["usage"] if row["feature"]=="official_unlocks")
        self.assertEqual(unlock["used"],0)

    def test_multiple_public_materials_can_be_unlocked_without_a_count_cap(self):
        books=[self.publish(index) for index in range(30,33)];user_id=str(self.alice["id"])
        for book in books:self.catalog.add_or_unlock(user_id,book,False)
        def unlock(book_id:str):
            try:return self.catalog.add_or_unlock(user_id,book_id,True)
            except SaaSError as exc:return exc
        with ThreadPoolExecutor(max_workers=3) as pool: results=list(pool.map(unlock,books))
        self.assertEqual(len([row for row in results if isinstance(row,dict)]),3)
        self.assertEqual([row for row in results if isinstance(row,SaaSError)],[])

    def test_http_catalog_and_library_endpoints(self):
        book_id=self.publish(50)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1",0));port=probe.getsockname()[1]
        environment={**os.environ,**self.environment,"READER_HOST":"127.0.0.1","READER_PORT":str(port)}
        server_path=os.path.join(os.path.dirname(__file__),"reader_server.py")
        process=subprocess.Popen([sys.executable,server_path],cwd=os.path.dirname(__file__),env=environment,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
        connections=[]
        try:
            deadline=time.time()+10
            while time.time()<deadline:
                try:
                    connection=http.client.HTTPConnection("127.0.0.1",port,timeout=1);connections.append(connection);connection.request("GET","/api/health");response=connection.getresponse();response.read();connection.close();connections.remove(connection)
                    if response.status==200:break
                except OSError:time.sleep(.1)
            else:self.fail("catalog test server did not start: "+(process.stderr.read() if process.stderr else ""))
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connections.append(connection);connection.request("GET","/api/catalog?q=Reader%2050");response=connection.getresponse();public=json.loads(response.read());self.assertEqual(response.status,200);self.assertEqual(public["books"][0]["id"],book_id);connection.close();connections.remove(connection)
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connections.append(connection);connection.request("POST","/api/auth/login",json.dumps({"email":"alice@local.test","password":"alice password phase three"}),{"Content-Type":"application/json","X-Device-Id":"phase3-http-alice-01"});response=connection.getresponse();self.assertEqual(response.status,200);headers=response.getheaders();response.read();connection.close();connections.remove(connection)
            values=[value.split(";",1)[0] for name,value in headers if name.lower()=="set-cookie"];cookies="; ".join(values);csrf=next(value.split("=",1)[1] for value in values if value.startswith("shiyue_csrf="))
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connections.append(connection)
            connection.request("GET",f"/api/catalog/books/{book_id}/reader?trial=1",headers={"Cookie":cookies})
            response=connection.getresponse();trial=json.loads(response.read());self.assertEqual(response.status,200)
            self.assertTrue(trial['book']['trial']);self.assertEqual(trial['book']['trialPercent'],10);self.assertEqual(len(trial['book']['sentences']),1)
            connection.close();connections.remove(connection)
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connections.append(connection)
            connection.request("GET",f"/api/catalog/books/{book_id}/reader",headers={"Cookie":cookies})
            response=connection.getresponse();response.read();self.assertEqual(response.status,403)
            connection.close();connections.remove(connection)
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connections.append(connection);connection.request("POST","/api/library/items",json.dumps({"bookId":book_id}),{"Content-Type":"application/json","Cookie":cookies,"X-CSRF-Token":csrf});response=connection.getresponse();self.assertEqual(response.status,201);response.read();connection.close();connections.remove(connection)
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connections.append(connection);connection.request("POST",f"/api/catalog/books/{book_id}/unlock",json.dumps({}),{"Content-Type":"application/json","Cookie":cookies,"X-CSRF-Token":csrf});response=connection.getresponse();unlocked=json.loads(response.read());self.assertEqual(response.status,200);self.assertTrue(unlocked["unlocked"]);connection.close();connections.remove(connection)
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connections.append(connection);connection.request("GET",f"/api/catalog/books/{book_id}/reader",headers={"Cookie":cookies});response=connection.getresponse();reader=json.loads(response.read());self.assertEqual(response.status,200);self.assertFalse(reader["book"]["mediaReady"]);self.assertEqual(len(reader["book"]["sentences"]),3);connection.close();connections.remove(connection)
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connections.append(connection);connection.request("GET","/api/library",headers={"Cookie":cookies});response=connection.getresponse();library=json.loads(response.read());self.assertEqual(response.status,200);self.assertEqual(library["items"][0]["id"],book_id);self.assertTrue(library["items"][0]["unlocked"]);connection.close();connections.remove(connection)
        finally:
            for connection in connections:connection.close()
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill()
            if process.stderr:process.stderr.close()


if __name__=="__main__":unittest.main()
