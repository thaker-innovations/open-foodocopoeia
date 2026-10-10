import csv
import hashlib
import json
from pathlib import Path
import unittest
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "public" / "data" / "v2026-10-10.2"


class PublishedDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((DATA / "manifest.json").read_text())
        cls.products = json.loads((DATA / "products.json").read_text())
        cls.quality = json.loads((DATA / "quality-parameters.json").read_text())
        cls.microbiological = json.loads((DATA / "microbiological-requirements.json").read_text())
        cls.pesticides = json.loads((DATA / "pesticide-residue-requirements.json").read_text())
        cls.heavy_metals = json.loads((DATA / "heavy-metal-requirements.json").read_text())
        cls.antibiotics = json.loads((DATA / "antibiotic-veterinary-drug-requirements.json").read_text())
        cls.contaminants = json.loads((DATA / "contaminant-requirements.json").read_text())
        cls.fatty_acids = json.loads((DATA / "fatty-acid-composition.json").read_text())
        cls.food_additives = json.loads((DATA / "food-additive-allowances.json").read_text())

    def test_manifest_counts_match_artifacts(self):
        counts = self.manifest["counts"]
        self.assertEqual(504, len(self.products))
        self.assertEqual(4923, len(self.quality))
        self.assertEqual(1809, len(self.microbiological))
        self.assertEqual(4044, len(self.pesticides))
        self.assertEqual(2729, len(self.heavy_metals))
        self.assertEqual(3777, len(self.antibiotics))
        self.assertEqual(712, len(self.contaminants))
        self.assertEqual(643, len(self.fatty_acids))
        self.assertEqual(452, len(self.food_additives))
        self.assertEqual(counts["products"], len(self.products))
        self.assertEqual(counts["quality_parameters"], len(self.quality))
        self.assertEqual(counts["microbiological_requirements"], len(self.microbiological))
        self.assertEqual(258, counts["products_with_microbiological_requirements"])
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

    def test_microbiological_csv_and_json_counts_match(self):
        with (DATA / "microbiological-requirements.csv").open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(self.microbiological), len(rows))
        product_ids = {product["id"] for product in self.products}
        self.assertTrue(all(row["product_id"] in product_ids for row in rows))

    def test_milk_has_separate_microbiological_requirements(self):
        milk = next(product for product in self.products if product["id"] == "266")
        self.assertEqual(23, len(milk["quality_parameters"]))
        self.assertEqual(10, len(milk["microbiological_requirements"]))
        aerobic = milk["microbiological_requirements"][0]
        self.assertEqual("Aerobic Plate Count", aerobic["parameter"])
        self.assertEqual(("5", "3", "30000", "50000"),
                         (aerobic["sampling_plan_n"], aerobic["sampling_plan_c"],
                          aerobic["limit_m"], aerobic["limit_M"]))
        self.assertEqual("mapped", aerobic["test_method_mapping_status"])

    def test_refined_oil_has_separate_residue_and_metal_requirements(self):
        oil = next(product for product in self.products if product["id"] == "72")
        self.assertEqual("Phenthoate", oil["pesticide_residue_requirements"][0]["analyte_or_requirement"])
        self.assertEqual("0.01", oil["pesticide_residue_requirements"][0]["limit_text"])
        self.assertEqual("Lead", oil["heavy_metal_requirements"][0]["analyte_or_requirement"])
        self.assertEqual("Total Aflatoxins", oil["contaminant_requirements"][0]["analyte_or_requirement"])

    def test_coconut_oil_has_fatty_acid_composition(self):
        coconut = next(product for product in self.products if product["id"] == "34")
        self.assertEqual(21, len(coconut["fatty_acid_composition"]))
        self.assertEqual("C6:0", coconut["fatty_acid_composition"][0]["fatty_acid"])

    def test_rice_product_retains_provenance(self):
        rice = next(product for product in self.products if product["id"] == "48")
        self.assertEqual("Rice", rice["name"])
        self.assertEqual(40, len(rice["quality_parameters"]))
        self.assertRegex(rice["provenance"]["source_sha256"], r"^[0-9a-f]{64}$")

    def test_static_product_pages_are_complete(self):
        home = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
        pages = list((ROOT / "public" / "products").glob("*/index.html"))
        rice = (ROOT / "public" / "products" / "48" / "index.html").read_text(encoding="utf-8")
        milk = (ROOT / "public" / "products" / "266" / "index.html").read_text(encoding="utf-8")
        oil = (ROOT / "public" / "products" / "72" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<script type="module" src="/search.js"></script>', home)
        self.assertEqual(504, len(pages))
        self.assertIn("<h1>Rice</h1>", rice)
        self.assertIn("General quality parameters", rice)
        self.assertIn('/api/v1/products/48', rice)
        self.assertNotIn("fetch(", rice)
        self.assertIn("Microbiological requirements", milk)
        self.assertIn("Aerobic Plate Count", milk)
        self.assertIn("CFU/ml", milk)
        self.assertIn("Pesticide and insecticide residues", oil)
        self.assertIn("Heavy metals", oil)
        self.assertIn("Phenthoate", oil)
        self.assertIn("Thaker Innovations Pvt. Ltd.", home)
        self.assertLess(home.index("Thaker Innovations Pvt. Ltd."), home.index("<header>"))
        self.assertIn('class="topline"', rice)

    def test_mcp_setup_is_published(self):
        setup = (ROOT / "public" / "mcp" / "setup" / "index.html").read_text(encoding="utf-8")
        self.assertIn("https://open-foodocopoeia.thakerinnovations.com/mcp", setup)
        self.assertIn("search_food_products", setup)
        self.assertIn("get_food_product", setup)
        self.assertIn("get_dataset_metadata", setup)

    def test_sitemap_uses_the_custom_subdomain(self):
        root = ElementTree.parse(ROOT / "public" / "sitemap.xml").getroot()
        namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        locations = [element.text for element in root.findall("s:url/s:loc", namespace)]
        self.assertEqual(507, len(locations))
        self.assertIn("https://open-foodocopoeia.thakerinnovations.com/products/48/", locations)
        self.assertIn("https://open-foodocopoeia.thakerinnovations.com/mcp/setup/", locations)
        self.assertTrue(all(url.startswith("https://open-foodocopoeia.thakerinnovations.com/") for url in locations))
        robots = (ROOT / "public" / "robots.txt").read_text(encoding="utf-8")
        self.assertIn("Sitemap: https://open-foodocopoeia.thakerinnovations.com/sitemap.xml", robots)


if __name__ == "__main__":
    unittest.main()
