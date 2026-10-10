#!/usr/bin/env python3
"""Build deterministic public API artifacts from normalized scraper JSONL."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil

REGULATORY_SECTIONS = (
    "pesticide_residue", "heavy_metal", "antibiotic_veterinary_drug", "contaminant",
)

DISCLAIMER = (
    "Unofficial independent project. Food-'O'-Copoeia is a ready reference; "
    "original FSS regulations, Gazette publications, and FSSAI directions prevail."
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def public_product(record: dict) -> dict:
    parameters = []
    for row in record.get("general_quality_parameters", []):
        parameters.append({key: row.get(key) for key in (
            "serial_number", "parameter", "variant", "fssr_limit", "test_method",
            "parser_strategy", "parsing_confidence", "source_table",
        )})
    microbiological = []
    for row in record.get("microbiological_requirements", []):
        microbiological.append({key: row.get(key) for key in (
            "serial_number", "parameter_type", "parameter_code", "parameter",
            "sampling_plan_n", "sampling_plan_c", "limit_m", "limit_M", "unit",
            "test_method", "test_method_mapping_status", "parser_strategy", "parsing_confidence",
        )})
    regulatory = {}
    for name in REGULATORY_SECTIONS:
        regulatory[f"{name}_status"] = record.get(f"{name}_status", "not_specified")
        regulatory[f"{name}_requirements"] = record.get(f"{name}_requirements", [])
        regulatory[f"{name}_text"] = record.get(f"{name}_text") or None
        regulatory[f"{name}_test_method_text"] = record.get(f"{name}_test_method_text") or None
    fatty_acid = [{key: row.get(key) for key in (
        "serial_number", "fatty_acid", "composition_limit", "test_method",
        "parser_strategy", "parsing_confidence",
    )} for row in record.get("fatty_acid_composition", [])]
    return {
        "id": str(record["identity"]),
        "name": record["product_name"],
        "name_source": record.get("product_name_source"),
        "category": {"name": record.get("category"), "reference": record.get("category_reference")},
        "subcategory": {"name": record.get("subcategory"), "reference": record.get("subcategory_reference")},
        "specific_subcategory": {
            "name": record.get("specific_subcategory"),
            "reference": record.get("specific_subcategory_reference"),
        },
        "quality_parameter_status": "available" if parameters else "not_specified",
        "quality_parameters": parameters,
        "microbiological_requirement_status": "available" if microbiological else "not_specified",
        "microbiological_requirements": microbiological,
        "microbiological_test_method_text": record.get("microbiological_test_method_text") or None,
        **regulatory,
        "food_additive_status": record.get("food_additive_status", "not_specified"),
        "food_additive_text": record.get("food_additive_text") or None,
        "fatty_acid_composition_status": "available" if fatty_acid else "not_specified",
        "fatty_acid_composition": fatty_acid,
        "test_method_reference_url": record.get("test_method_reference_url"),
        "manual_reviewed": any(row.get("parser_strategy") == "manual_override" for row in parameters),
        "provenance": {
            "source_url": record.get("source_url"),
            "retrieved_at": record.get("retrieved_at"),
            "source_sha256": record.get("source_sha256"),
        },
    }


def build(input_path: Path, public: Path, snapshot: str) -> dict:
    records = [json.loads(line) for line in input_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    products = sorted((public_product(record) for record in records), key=lambda p: int(p["id"]))
    if len(products) != len({product["id"] for product in products}):
        raise ValueError("Duplicate product identities")

    snapshot_root = public / "data" / f"v{snapshot}"
    product_root = snapshot_root / "products"
    product_root.mkdir(parents=True, exist_ok=True)
    for product in products:
        write_json(product_root / f"{product['id']}.json", {
            "unofficial": True, "snapshot": snapshot, "disclaimer": DISCLAIMER, "product": product,
        })

    summaries = []
    for product in products:
        summary = {
            "id": product["id"], "name": product["name"], "category": product["category"]["name"],
            "subcategory": product["subcategory"]["name"],
            "specific_subcategory": product["specific_subcategory"]["name"],
            "quality_parameter_status": product["quality_parameter_status"],
            "quality_parameter_count": len(product["quality_parameters"]),
            "microbiological_requirement_status": product["microbiological_requirement_status"],
            "microbiological_requirement_count": len(product["microbiological_requirements"]),
            "food_additive_status": product["food_additive_status"],
            "fatty_acid_composition_status": product["fatty_acid_composition_status"],
            "fatty_acid_composition_count": len(product["fatty_acid_composition"]),
        }
        for name in REGULATORY_SECTIONS:
            summary[f"{name}_status"] = product[f"{name}_status"]
            summary[f"{name}_requirement_count"] = len(product[f"{name}_requirements"])
        summaries.append(summary)
    write_json(snapshot_root / "products.json", products)

    quality_rows = []
    for product in products:
        for row in product["quality_parameters"]:
            quality_rows.append({
                "product_id": product["id"], "product_name": product["name"],
                "category": product["category"]["name"],
                "subcategory": product["subcategory"]["name"],
                "specific_subcategory": product["specific_subcategory"]["name"], **row,
            })
    write_json(snapshot_root / "quality-parameters.json", quality_rows)

    microbiological_rows = []
    for product in products:
        for row in product["microbiological_requirements"]:
            microbiological_rows.append({
                "product_id": product["id"], "product_name": product["name"],
                "category": product["category"]["name"],
                "subcategory": product["subcategory"]["name"],
                "specific_subcategory": product["specific_subcategory"]["name"],
                **row,
                "source_url": product["provenance"]["source_url"],
                "retrieved_at": product["provenance"]["retrieved_at"],
                "source_sha256": product["provenance"]["source_sha256"],
            })
    write_json(snapshot_root / "microbiological-requirements.json", microbiological_rows)

    regulatory_rows = {name: [] for name in REGULATORY_SECTIONS}
    fatty_acid_rows = []
    food_additive_rows = []
    for product in products:
        common = {
            "product_id": product["id"], "product_name": product["name"],
            "category": product["category"]["name"],
            "subcategory": product["subcategory"]["name"],
            "specific_subcategory": product["specific_subcategory"]["name"],
        }
        provenance = {
            "source_url": product["provenance"]["source_url"],
            "retrieved_at": product["provenance"]["retrieved_at"],
            "source_sha256": product["provenance"]["source_sha256"],
        }
        for name in REGULATORY_SECTIONS:
            for row in product[f"{name}_requirements"]:
                regulatory_rows[name].append({**common, **row, **provenance})
        for row in product["fatty_acid_composition"]:
            fatty_acid_rows.append({**common, **row, **provenance})
        if product["food_additive_status"] == "available":
            food_additive_rows.append({**common, "allowance_text": product["food_additive_text"], **provenance})

    artifact_rows = {
        "pesticide-residue-requirements": regulatory_rows["pesticide_residue"],
        "heavy-metal-requirements": regulatory_rows["heavy_metal"],
        "antibiotic-veterinary-drug-requirements": regulatory_rows["antibiotic_veterinary_drug"],
        "contaminant-requirements": regulatory_rows["contaminant"],
        "fatty-acid-composition": fatty_acid_rows,
        "food-additive-allowances": food_additive_rows,
    }
    for name, rows in artifact_rows.items():
        write_json(snapshot_root / f"{name}.json", rows)

    with (snapshot_root / "products.csv").open("w", newline="", encoding="utf-8") as handle:
        columns = list(summaries[0])
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader(); writer.writerows(summaries)
    with (snapshot_root / "quality-parameters.csv").open("w", newline="", encoding="utf-8") as handle:
        columns = list(quality_rows[0])
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader(); writer.writerows(quality_rows)
    with (snapshot_root / "microbiological-requirements.csv").open("w", newline="", encoding="utf-8") as handle:
        columns = list(microbiological_rows[0])
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader(); writer.writerows(microbiological_rows)
    for name, rows in artifact_rows.items():
        with (snapshot_root / f"{name}.csv").open("w", newline="", encoding="utf-8") as handle:
            columns = list(rows[0])
            writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
            writer.writeheader(); writer.writerows(rows)

    search_index = [{
        "id": p["id"], "name": p["name"], "category": p["category"]["name"],
        "subcategory": p["subcategory"]["name"],
        "specific_subcategory": p["specific_subcategory"]["name"],
    } for p in products]
    write_json(public.parent / "worker" / "generated" / "search-index.json", search_index)
    (public.parent / "worker" / "generated" / "snapshot.ts").write_text(
        f'export const SNAPSHOT = "{snapshot}";\n', encoding="utf-8")

    files = [snapshot_root / name for name in (
        "products.json", "products.csv", "quality-parameters.json", "quality-parameters.csv",
        "microbiological-requirements.json", "microbiological-requirements.csv",
        *(f"{name}.{extension}" for name in artifact_rows for extension in ("json", "csv")),
    )]
    retrieved = sorted({p["provenance"]["retrieved_at"] for p in products if p["provenance"]["retrieved_at"]})
    code_data = json.loads((public.parent / "scraper" / "parameter_codes.json").read_text(encoding="utf-8"))
    reference_dictionaries = {
        name: {
            "source_url": details["source_url"],
            "source_sha256": details["source_sha256"],
            "entries": len(details["entries"]),
        } for name, details in code_data["dictionaries"].items()
    }
    manifest = {
        "schema_version": "1.2.0", "dataset_version": snapshot, "unofficial": True,
        "disclaimer": DISCLAIMER, "source": "https://foodocopoeia.fssai.gov.in/Home.aspx",
        "retrieved_at_range": [retrieved[0], retrieved[-1]] if retrieved else [],
        "reference_dictionaries": reference_dictionaries,
        "counts": {
            "products": len(products),
            "products_with_quality_parameters": sum(p["quality_parameter_status"] == "available" for p in products),
            "quality_parameters": len(quality_rows),
            "products_with_microbiological_requirements": sum(p["microbiological_requirement_status"] == "available" for p in products),
            "microbiological_requirements": len(microbiological_rows),
            "microbiological_methods_mapped": sum(row["test_method_mapping_status"] == "mapped" for row in microbiological_rows),
            "microbiological_methods_unresolved": sum(row["test_method_mapping_status"] != "mapped" for row in microbiological_rows),
            **{
                f"products_with_{name}_requirements": sum(p[f"{name}_status"] in {"available", "narrative"} for p in products)
                for name in REGULATORY_SECTIONS
            },
            **{f"{name}_requirements": len(regulatory_rows[name]) for name in REGULATORY_SECTIONS},
            "products_with_food_additive_allowances": len(food_additive_rows),
            "food_additive_allowances": len(food_additive_rows),
            "products_with_fatty_acid_composition": sum(p["fatty_acid_composition_status"] == "available" for p in products),
            "fatty_acid_composition_rows": len(fatty_acid_rows),
            "manually_reviewed_products": sum(p["manual_reviewed"] for p in products),
        },
        "files": {path.name: {"sha256": sha256(path), "bytes": path.stat().st_size} for path in files},
    }
    write_json(snapshot_root / "manifest.json", manifest)
    write_json(public / "data" / "manifest.json", manifest)

    latest = public / "downloads" / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    for path in files:
        shutil.copyfile(path, latest / path.name)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("work/products.jsonl"))
    parser.add_argument("--public", type=Path, default=Path("public"))
    parser.add_argument("--snapshot", default="2026-10-10.2")
    args = parser.parse_args()
    print(json.dumps(build(args.input, args.public, args.snapshot), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
