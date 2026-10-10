import csv
import hashlib
import json
from pathlib import Path
import unittest

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

    def test_static_interface_links_search_to_product_view(self):
        home = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
        product = (ROOT / "public" / "product" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<script type="module" src="/search.js"></script>', home)
        self.assertIn("/api/v1/products/", product)
        self.assertIn("General quality parameters", product)


if __name__ == "__main__":
    unittest.main()
