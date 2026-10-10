import csv
import hashlib
import json
from pathlib import Path
import unittest
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "public" / "data" / "v2026-10-10"


class PublishedDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((DATA / "manifest.json").read_text())
        cls.products = json.loads((DATA / "products.json").read_text())
        cls.quality = json.loads((DATA / "quality-parameters.json").read_text())

    def test_manifest_counts_match_artifacts(self):
        counts = self.manifest["counts"]
        self.assertEqual(504, len(self.products))
        self.assertEqual(4923, len(self.quality))
        self.assertEqual(counts["products"], len(self.products))
        self.assertEqual(counts["quality_parameters"], len(self.quality))
        self.assertEqual(counts["products_with_quality_parameters"],
                         sum(p["quality_parameter_status"] == "available" for p in self.products))
        self.assertEqual(counts["manually_reviewed_products"],
                         sum(p["manual_reviewed"] for p in self.products))

    def test_identities_and_per_product_documents_are_complete(self):
        identities = [p["id"] for p in self.products]
        self.assertEqual(len(identities), len(set(identities)))
        files = {path.stem for path in (DATA / "products").glob("*.json")}
        self.assertEqual(set(identities), files)

    def test_manifest_checksums_match(self):
        for name, metadata in self.manifest["files"].items():
            path = DATA / name
            self.assertEqual(metadata["bytes"], path.stat().st_size)
            self.assertEqual(metadata["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_csv_and_json_row_counts_match(self):
        with (DATA / "products.csv").open(encoding="utf-8") as handle:
            self.assertEqual(len(self.products), len(list(csv.DictReader(handle))))
        with (DATA / "quality-parameters.csv").open(encoding="utf-8") as handle:
            self.assertEqual(len(self.quality), len(list(csv.DictReader(handle))))

    def test_rice_product_retains_provenance(self):
        rice = next(product for product in self.products if product["id"] == "48")
        self.assertEqual("Rice", rice["name"])
        self.assertEqual(40, len(rice["quality_parameters"]))
        self.assertRegex(rice["provenance"]["source_sha256"], r"^[0-9a-f]{64}$")

    def test_static_product_pages_are_complete(self):
        home = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
        pages = list((ROOT / "public" / "products").glob("*/index.html"))
        rice = (ROOT / "public" / "products" / "48" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<script type="module" src="/search.js"></script>', home)
        self.assertEqual(504, len(pages))
        self.assertIn("<h1>Rice</h1>", rice)
        self.assertIn("General quality parameters", rice)
        self.assertIn('/api/v1/products/48', rice)
        self.assertNotIn("fetch(", rice)

    def test_sitemap_uses_the_custom_subdomain(self):
        root = ElementTree.parse(ROOT / "public" / "sitemap.xml").getroot()
        namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        locations = [element.text for element in root.findall("s:url/s:loc", namespace)]
        self.assertEqual(506, len(locations))
        self.assertIn("https://open-foodocopoeia.thakerinnovations.com/products/48/", locations)
        self.assertTrue(all(url.startswith("https://open-foodocopoeia.thakerinnovations.com/") for url in locations))
        robots = (ROOT / "public" / "robots.txt").read_text(encoding="utf-8")
        self.assertIn("Sitemap: https://open-foodocopoeia.thakerinnovations.com/sitemap.xml", robots)


if __name__ == "__main__":
    unittest.main()
