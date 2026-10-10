#!/usr/bin/env python3
import csv
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scraper" / "foodocopoeia.py"
SPEC = importlib.util.spec_from_file_location("fssai_foodocopoeia", MODULE_PATH)
fssai = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fssai)


LISTING = b"""
<form><input type="hidden" name="__VIEWSTATE" value="state">
<table id="gvApplication"><tr><th>Category</th></tr><tr>
<td><span id="gvApplication_lblcategory_0">CEREALS</span>
<input type="hidden" id="gvApplication_hdncatcode_0" value="0204">
<input type="hidden" id="gvApplication_hdnidentity_0" value="42"></td>
<td><span id="gvApplication_lblsubcategory_0">Pulses</span>
<input type="hidden" id="gvApplication_hdnSubcatcode_0" value="020401"></td>
<td><span id="gvApplication_lblSpSubCat_0">Pulse flour</span>
<input type="hidden" id="gvApplication_hdnSpSubCatcode_0" value="02040101"></td>
<td><a id="gvApplication_lnk_View_0" href="javascript:__doPostBack('gvApplication$ctl02$lnk_View','')">View</a></td>
</tr></table></form>
"""

DETAIL = b"""
<span id="LblFPHeader">FOOD STANDARDS: PULSE FLOUR</span>
<span id="LblCatRefCode">FC-2.4</span><span id="LblCategory">CEREALS</span>
<span id="LblSubCatRefCode">FC-2.4.1</span><span id="LblSubCategory">Pulses</span>
<span id="LblSpSubCatRefCode">FC-2.4.1.1</span><span id="LblSpSubCategory">Pulse flour</span>
<table id="GVGenQualityParams"><tr><th>SrNo.</th><th>Parameter</th><th>FSSR Limit</th><th>Test Method</th></tr>
<tr><td>1</td><td><span id="GVGenQualityParams_lblParamName_0">Moisture (% by mass), not more than</span></td>
<td><span id="GVGenQualityParams_lblParamFSSRLimitVal_0">12</span></td>
<td><span id="GVGenQualityParams_lblParamTestMethodVal_0">FSSAI 03.006:2023</span></td></tr>
<tr><td>2</td><td><span id="GVGenQualityParams_lblParamName_1">Protein (N x 6.25), not less than</span></td>
<td><span id="GVGenQualityParams_lblParamFSSRLimitVal_1">8.5</span></td>
<td><span id="GVGenQualityParams_lblParamTestMethodVal_1">FSSAI 03.017:2023</span></td></tr></table>
<a id="lnk_URL" href="https://example.test/methods.pdf">Methods</a>
<span id="LblFss232">This unrelated safety field must not be normalized.</span>
"""


class FoodOCopoeiaTests(unittest.TestCase):
    def listing(self):
        fields, products = fssai.parse_listing(LISTING, "P")
        self.assertEqual("state", fields["__VIEWSTATE"])
        self.assertEqual(1, len(products))
        return products[0]

    def test_listing_extracts_stable_identity_and_postback(self):
        product = self.listing()
        self.assertEqual("42", product["identity"])
        self.assertEqual("gvApplication$ctl02$lnk_View", product["event_target"])
        self.assertEqual("Pulse flour", product["specific_subcategory"])

    def test_detail_extracts_only_general_quality_parameters(self):
        record = fssai.parse_detail(DETAIL, self.listing(), hashlib.sha256(DETAIL).hexdigest())
        self.assertEqual("Pulse flour", record["specific_subcategory"])
        self.assertEqual("https://example.test/methods.pdf", record["test_method_reference_url"])
        parameters = record["general_quality_parameters"]
        self.assertEqual(2, len(parameters))
        self.assertEqual("Moisture (% by mass), not more than", parameters[0]["parameter"])
        self.assertEqual("12", parameters[0]["fssr_limit"])
        self.assertEqual("FSSAI 03.006:2023", parameters[0]["test_method"])
        self.assertEqual("standard_grid", parameters[0]["parser_strategy"])
        self.assertEqual("high", parameters[0]["parsing_confidence"])
        self.assertNotIn("antibiotic_vdr_limits", record)

    def test_alternate_variant_table_expands_limits_without_guessing(self):
        rows = [
            ["S. No", "Parameter", "Fresh", "Processed", "Test method"],
            ["1", "Brix (Min.)", "14.0", "12.0", "NS"],
            ["2", "pH", "6.0-7.5", "5.0-7.5", "IS 3025"],
        ]
        parsed = fssai.parse_simple_alternate_table(rows)
        self.assertEqual(4, len(parsed))
        self.assertEqual(("Brix (Min.)", "Fresh", "14.0"),
                         (parsed[0]["parameter"], parsed[0]["variant"], parsed[0]["fssr_limit"]))
        self.assertEqual(("pH", "Processed", "5.0-7.5"),
                         (parsed[3]["parameter"], parsed[3]["variant"], parsed[3]["fssr_limit"]))
        self.assertEqual("alternate_variant_table", parsed[0]["parser_strategy"])

    def test_complex_transposed_table_is_left_for_manual_review(self):
        rows = [
            ["SL. NO", "NAME", "BOTANICAL NAME", "FSSR PARAMETERS"],
            ["Brix [Method A]", "Acidity [Method B]"],
            ["1", "Cashewapple", "Anacardium", "11.5", "3.5"],
        ]
        self.assertIsNone(fssai.parse_simple_alternate_table(rows))

    def test_ambiguous_others_name_includes_its_hierarchy(self):
        self.assertEqual(
            "Others — Coffee (BEVERAGES)",
            fssai.qualified_product_name({
                "specific_subcategory": "Others", "subcategory": "Coffee", "category": "BEVERAGES",
            }),
        )
        fallback = {"specific_subcategory": "N/A", "subcategory": "Pulses", "category": "CEREALS"}
        self.assertEqual("Pulses", fssai.qualified_product_name(fallback))
        self.assertEqual(("Pulses", "subcategory"), fssai.qualified_product(fallback))
        self.assertEqual(
            ("RUM", "category"),
            fssai.qualified_product({
                "specific_subcategory": "N/A", "subcategory": "N/A", "category": "RUM",
            }),
        )

    def test_manual_override_replaces_automatic_rows(self):
        record = fssai.parse_detail(DETAIL, self.listing(), hashlib.sha256(DETAIL).hexdigest())
        fssai.apply_manual_overrides([record], {"42": {
            "identity": "42",
            "review_note": "Reviewed table",
            "quality_parameters": [{
                "parameter": "Reviewed moisture", "variant": "Type A",
                "fssr_limit": "10", "test_method": "Manual 1", "source_table": 2,
            }],
        }})
        self.assertEqual(1, len(record["general_quality_parameters"]))
        row = record["general_quality_parameters"][0]
        self.assertEqual("Reviewed moisture", row["parameter"])
        self.assertEqual("manual_override", row["parser_strategy"])
        self.assertEqual("reviewed", row["parsing_confidence"])

    def test_master_csv_has_one_row_per_parameter(self):
        record = fssai.parse_detail(DETAIL, self.listing(), hashlib.sha256(DETAIL).hexdigest())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fssai.write_csv_files(root, [record])
            with (root / "quality_parameters.csv").open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(2, len(rows))
            self.assertEqual("42", rows[0]["identity"])
            self.assertEqual("Pulse flour", rows[0]["product_name"])
            self.assertEqual("specific_subcategory", rows[0]["product_name_source"])
            self.assertEqual("12", rows[0]["fssr_limit"])


if __name__ == "__main__":
    unittest.main()
