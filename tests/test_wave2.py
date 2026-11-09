import unittest
from unittest import mock

from deep_reach.backends.epo import _cql, _documents, _search
from deep_reach.backends.epo import _item as epo_item
from deep_reach.backends.uspto import _item as uspto_item
from deep_reach.channels import load_registry
from deep_reach.runtime.keys import Keys


class UsptoParseTest(unittest.TestCase):
    def test_item(self):
        row = {
            "applicationNumberText": "17123456",
            "applicationMetaData": {
                "inventionTitle": "Desk organizer",
                "firstApplicantName": "ACME",
                "filingDate": "2022-01-02",
                "grantDate": "2024-03-04",
                "patentNumber": "11999999",
                "applicationStatusDescriptionText": "Patented Case",
            },
        }
        item = uspto_item(row)
        self.assertEqual(item["source"], "uspto")
        self.assertEqual(item["title"], "Desk organizer")
        self.assertEqual(item["author"], "ACME")
        self.assertEqual(
            item["url"], "https://patents.google.com/patent/US11999999"
        )
        self.assertEqual(item["metrics"]["application_number"], "17123456")
        self.assertEqual(item["metrics"]["status"], "Patented Case")

    def test_application_url_without_patent_number(self):
        item = uspto_item(
            {
                "applicationNumberText": "17123456",
                "applicationMetaData": {"inventionTitle": "Pending"},
            }
        )
        self.assertIn("patentcenter.uspto.gov", item["url"])


EPO_PAYLOAD = {
    "ops:world-patent-data": {
        "ops:biblio-search": {
            "@total-result-count": "1",
            "ops:search-result": {
                "exchange-documents": [
                    {
                        "exchange-document": {
                            "@country": "EP",
                            "@doc-number": "1234567",
                            "@kind": "A1",
                            "@family-id": "999",
                            "bibliographic-data": {
                                "invention-title": [
                                    {"@lang": "de", "$": "Titel"},
                                    {"@lang": "en", "$": "Desk organizer"},
                                ],
                                "publication-reference": {
                                    "document-id": [{"date": {"$": "20240102"}}]
                                },
                                "parties": {
                                    "applicants": {
                                        "applicant": [
                                            {"name": {"$": "ACME GmbH"}}
                                        ]
                                    },
                                    "inventors": {
                                        "inventor": [{"name": {"$": "Jane Doe"}}]
                                    },
                                },
                            },
                        }
                    }
                ]
            },
        }
    }
}


class EpoParseTest(unittest.TestCase):
    def test_documents_and_item(self):
        docs, total = _documents(EPO_PAYLOAD)
        self.assertEqual(total, 1)
        self.assertEqual(len(docs), 1)
        item = epo_item(docs[0])
        self.assertEqual(item["source"], "epo")
        self.assertEqual(item["title"], "Desk organizer")
        self.assertEqual(item["author"], "ACME GmbH")
        self.assertEqual(item["published_at"], "2024-01-02")
        self.assertEqual(item["metrics"]["country"], "EP")
        self.assertIn("EP1234567", item["url"])

    def test_cql(self):
        self.assertEqual(_cql("desk organizer"), 'ta="desk organizer"')
        self.assertEqual(_cql('a "quoted" thing'), 'ta="a  quoted  thing"')


class EpoRequestTest(unittest.TestCase):
    def test_search_sends_range_as_query_parameter(self):
        captured = {}

        def fake_fetch_json(url, **kwargs):
            captured["url"] = url
            captured["kwargs"] = kwargs
            return EPO_PAYLOAD

        keys = Keys(
            {
                "official": {
                    "epo": {"consumer_key": "key", "consumer_secret": "secret"}
                }
            }
        )
        with mock.patch(
            "deep_reach.backends.epo.fetch_json", side_effect=fake_fetch_json
        ):
            items = _search(
                'ta="desk organizer"', 5, 10.0, keys, {"access_token": "token"}
            )

        self.assertEqual(len(items), 1)
        self.assertEqual(captured["kwargs"]["params"]["Range"], "1-5")
        self.assertNotIn("Range", captured["kwargs"].get("headers", {}))


class Wave2RegistryTest(unittest.TestCase):
    def test_channels(self):
        registry = load_registry()
        for name in ("uspto", "epo"):
            self.assertIn(name, registry.visible)
            channel = registry.visible[name]
            self.assertEqual(channel.status, "needs_key")
            self.assertIn("p0", channel.tiers)
        self.assertNotIn("indiegogo", registry.all())


if __name__ == "__main__":
    unittest.main()
