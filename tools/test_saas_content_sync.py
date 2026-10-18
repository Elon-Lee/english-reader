#!/usr/bin/env python3
"""Content uploads require destination review, including replay and revision cases."""
import copy
import gzip
import json
import os
from pathlib import Path
import tempfile
import unittest

from deployment.saas_public_sync import apply_bundle, content_fingerprints, export_bundle, pending_catalog
import test_saas_phase3_integration as phase3


class ContentFingerprintTests(unittest.TestCase):
    def tables(self):
        return {"catalog_books":[{"id":"book","source_content_book_id":"source","publication_status":"published","reviewed_by":"local-admin","published_at":"2026-10-18"}],
                "content_books":[{"id":"source","data_json":{"sentences":[{"text":"Original"}]}}],
                "media_assets":[],"asset_variants":[],"catalog_series":[],"catalog_tags":[],"catalog_book_tags":[],"content_sentence_grammar":[]}

    def test_upload_clears_local_review_without_mutating_original(self):
        original=self.tables()["catalog_books"]
        pending=pending_catalog(original)[0]
        self.assertEqual(pending["publication_status"],"draft")
        self.assertIsNone(pending["reviewed_by"])
        self.assertIsNone(pending["published_at"])
        self.assertEqual(original[0]["publication_status"],"published")

    def test_local_review_does_not_change_content_revision(self):
        tables=self.tables();before=content_fingerprints(tables)
        tables["catalog_books"][0].update(publication_status="archived",reviewed_by=None,published_at=None)
        self.assertEqual(content_fingerprints(tables),before)

    def test_changed_text_or_media_invalidates_review(self):
        tables=self.tables();before=content_fingerprints(tables)
        changed=copy.deepcopy(tables)
        changed["content_books"][0]["data_json"]["sentences"][0]["text"]="Changed"
        self.assertNotEqual(content_fingerprints(changed),before)
        tables["media_assets"]=[{"id":"asset","content_book_id":"source","sha256":"one"}]
        before=content_fingerprints(tables)
        tables["media_assets"][0]["sha256"]="two"
        self.assertNotEqual(content_fingerprints(tables),before)


@unittest.skipUnless(os.environ.get("SHIYUE_SAAS_TEST_DATABASE_URL"),"requires an isolated _test PostgreSQL database")
class ContentUploadPostgresTests(unittest.TestCase):
    setUpClass=classmethod(phase3.PhaseThreePostgresTests.setUpClass.__func__)
    setUp=phase3.PhaseThreePostgresTests.setUp
    verify=phase3.PhaseThreePostgresTests.verify
    source=phase3.PhaseThreePostgresTests.source
    publish=phase3.PhaseThreePostgresTests.publish

    def export(self,root):
        bundle=root/"content.json.gz";manifest=root/"manifest.json"
        export_bundle(phase3.TEST_URL,root,bundle,manifest)
        return bundle,manifest

    def test_upload_review_replay_and_changed_revision(self):
        book_id=self.publish(70)
        self.source(71)  # Unstaged private content must never be uploaded.
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);bundle,manifest=self.export(root)
            payload=json.loads(gzip.decompress(bundle.read_bytes()))
            self.assertEqual([row["id"] for row in payload["tables"]["content_books"]],["source-70"])
            self.assertEqual(payload["tables"]["catalog_books"][0]["publication_status"],"draft")
            # Apply also defends against old bundles carrying local approval.
            payload["tables"]["catalog_books"][0].update(publication_status="published",reviewed_by=self.admin["id"])
            bundle.write_bytes(gzip.compress(json.dumps(payload).encode()))
            self.assertEqual(apply_bundle(phase3.TEST_URL,bundle)["pendingReviewBooks"],1)
            self.assertEqual(self.catalog.catalog()["books"],[])
            row=next(item for item in self.catalog.review_sources()["sources"] if item["catalogBookId"]==book_id)
            self.assertEqual(row["publicationStatus"],"draft")
            self.catalog.review(str(self.admin["id"]),"source-70","licensed","published",{"author":"Online author","description":"Online description","tags":["Online tag"]})
            self.assertEqual(len(self.catalog.catalog()["books"]),1)
            self.assertEqual(apply_bundle(phase3.TEST_URL,bundle,manifest)["pendingReviewBooks"],0)
            self.assertEqual(self.catalog.detail(book_id)["book"]["author"],"Online author")
            self.assertEqual([item["title"] for item in self.catalog.detail(book_id)["book"]["tags"]],["Online tag"])
            self.assertEqual(len(self.catalog.catalog()["books"]),1)
            payload["tables"]["content_books"][0]["data_json"]["sentences"][0]["text"]="Revised upload"
            bundle.write_bytes(gzip.compress(json.dumps(payload).encode()))
            self.assertEqual(apply_bundle(phase3.TEST_URL,bundle,manifest)["pendingReviewBooks"],1)
            self.assertEqual(self.catalog.catalog()["books"],[])

    def test_staged_unreviewed_content_can_be_uploaded(self):
        source=self.source(72)
        self.catalog.review(str(self.admin["id"]),source,"private","draft",{})
        with tempfile.TemporaryDirectory() as directory:
            bundle,_=self.export(Path(directory))
            payload=json.loads(gzip.decompress(bundle.read_bytes()))
            self.assertEqual(len(payload["tables"]["catalog_books"]),1)
            self.assertEqual(payload["tables"]["catalog_books"][0]["publication_status"],"draft")
            apply_bundle(phase3.TEST_URL,bundle)
            self.assertEqual(self.catalog.catalog()["books"],[])


if __name__=="__main__":unittest.main()
