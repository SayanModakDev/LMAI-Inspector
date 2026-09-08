"""Tests for Semantic Field Ownership, Boundary Isolation, Date Precision,
Multipack Retention, and Result Aggregation Consistency.
"""
import pytest
from app.extraction.declaration_extractor import extract_declarations
from app.rules.rule_engine import evaluate_rules, calculate_rule_summary, derive_overall_result
from app.core.ontology import DatePrecision, ContactType


class TestSemanticFieldOwnership:

    def test_a_product_name_scoping_and_ambiguity(self):
        """TEST A: Product Name Scoping & Ambiguity.
        When multiple generic/brand lines compete without explicit front-panel hierarchy,
        structured ambiguity is preserved and only the product name rule is NOT_VERIFIABLE.
        """
        raw_text = (
            "Aura Botanics\n"
            "Pure Herbal Extract\n"
            "Natural Glow\n"
            "Net Wt: 100 g"
        )
        fields = extract_declarations(raw_text)

        pname = fields.get("PRODUCT_NAME")
        assert pname is not None, "PRODUCT_NAME candidate should be generated"
        assert pname.get("status") in ("AMBIGUOUS", "REVIEW")
        competing = pname.get("competing_candidates", [])
        assert len(competing) >= 2, f"Expected >= 2 competing candidates, got {competing}"
        assert any("Aura Botanics" in c for c in competing)
        assert any("Pure Herbal Extract" in c for c in competing)

        rules = [
            {
                "rule_id": "PC-ALL-001",
                "rule_name": "Product Name Declaration",
                "parameter": "PRODUCT_NAME",
                "required": True,
                "is_active": True,
            },
            {
                "rule_id": "PC-ALL-004",
                "rule_name": "Net Quantity Declaration",
                "parameter": "DECLARED_NET_QUANTITY",
                "required": True,
                "is_active": True,
            },
        ]
        results, overall = evaluate_rules(rules, fields)
        by_id = {r["rule_id"]: r for r in results}

        assert by_id["PC-ALL-001"]["status"] == "NOT_VERIFIABLE"
        assert by_id["PC-ALL-004"]["status"] == "PASS"

    def test_b_manufacturer_and_address_clean_separation(self):
        """TEST B: Manufacturer & Address Clean Separation.
        Vendor line terminates before physical location, and address excludes corporate name,
        consumer care contact details, and quantity declarations.
        """
        raw_text = (
            "Manufactured by:\n"
            "Sunrise Agro Foods Pvt Ltd\n"
            "Plot 14, Industrial Area, Phase II,\n"
            "Ahmedabad, Gujarat 382445\n"
            "Customer Care: 1800-200-4000\n"
            "Net Qty: 500 g"
        )
        fields = extract_declarations(raw_text)

        mfg_name = fields.get("MANUFACTURER_NAME", {}).get("value", "")
        mfg_addr = fields.get("MANUFACTURER_ADDRESS", {}).get("value", "")

        assert "Sunrise Agro Foods Pvt Ltd" in mfg_name
        assert "Plot 14" not in mfg_name
        assert "Ahmedabad" not in mfg_name
        assert "1800" not in mfg_name

        assert "Plot 14" in mfg_addr
        assert "Ahmedabad" in mfg_addr
        assert "Gujarat" in mfg_addr

        assert "Sunrise Agro Foods Pvt Ltd" not in mfg_addr
        assert "1800-200-4000" not in mfg_addr
        assert "Customer Care" not in mfg_addr
        assert "Net Qty" not in mfg_addr
        assert "500 g" not in mfg_addr

    def test_c_consumer_care_clean_contact_extraction(self):
        """TEST C: Consumer Care Clean Contact Extraction.
        Structured channels (toll-free, phone, email, etc.) are extracted cleanly,
        and unrelated neighboring lines (batch numbers, etc.) are completely excluded.
        """
        raw_text = (
            "Consumer Care: Call 1800-222-333 or email care@healthyfoods.com\n"
            "Batch No: B-9981"
        )
        fields = extract_declarations(raw_text)

        cc = fields.get("CONSUMER_CARE")
        assert cc is not None, "CONSUMER_CARE should be present"
        assert cc.get("primary_contact_type") in ("TOLL_FREE", "PHONE")
        
        contacts = cc.get("contacts", [])
        assert any(c.get("contact_type") in ("TOLL_FREE", "PHONE") for c in contacts)
        assert any(c.get("contact_type") == "EMAIL" for c in contacts)

        cc_str = str(cc)
        assert "Batch No" not in cc_str
        assert "B-9981" not in cc_str

    def test_d_full_date_precision_and_no_duplication(self):
        """TEST D: Date Precision & Deduplication (Full Date).
        Full date (DD/MM/YYYY) emits MANUFACTURE_DATE with precision FULL_DATE.
        MONTH_YEAR_MANUFACTURE must be completely absent.
        Rule PC-ALL-009 evaluates to PASS.
        """
        raw_text = "Mfg Date: 25/08/2024"
        fields = extract_declarations(raw_text)

        mfg_date = fields.get("MANUFACTURE_DATE")
        assert mfg_date is not None, "MANUFACTURE_DATE must be present"
        assert mfg_date.get("value") == "25/08/2024" or mfg_date.get("raw_date") == "25/08/2024"
        assert mfg_date.get("precision") == "FULL_DATE"

        assert "MONTH_YEAR_MANUFACTURE" not in fields, "MONTH_YEAR_MANUFACTURE must be absent when full date is declared"

        rules = [
            {
                "rule_id": "PC-ALL-009",
                "rule_name": "Date of Manufacture/Packing",
                "parameter": "MANUFACTURE_DATE",
                "required": True,
                "is_active": True,
            }
        ]
        results, overall = evaluate_rules(rules, fields)
        assert results[0]["status"] == "PASS"

    def test_e_month_year_precision_and_no_duplication(self):
        """TEST E: Date Precision & Deduplication (Month/Year).
        Month/Year date (MM/YYYY) emits MONTH_YEAR_MANUFACTURE with precision MONTH_YEAR.
        MANUFACTURE_DATE must be completely absent.
        Rule PC-ALL-009 evaluates to PASS.
        """
        raw_text = "Mfg Date: 08/2024"
        fields = extract_declarations(raw_text)

        my_date = fields.get("MONTH_YEAR_MANUFACTURE")
        assert my_date is not None, "MONTH_YEAR_MANUFACTURE must be present"
        assert my_date.get("value") == "08/2024" or my_date.get("raw_date") == "08/2024"
        assert my_date.get("precision") == "MONTH_YEAR"

        assert "MANUFACTURE_DATE" not in fields, "MANUFACTURE_DATE must be absent when only month/year is declared"

        rules = [
            {
                "rule_id": "PC-ALL-009",
                "rule_name": "Date of Manufacture/Packing",
                "parameter": "MONTH_YEAR_MANUFACTURE",
                "required": True,
                "is_active": True,
            }
        ]
        results, overall = evaluate_rules(rules, fields)
        assert results[0]["status"] == "PASS"

    def test_f_multipack_regression_retention(self):
        """TEST F: Multipack Regression Retention.
        Expression COUNT × UNIT QUANTITY must retain multipack fields,
        derived total, and unit quantity without collapsing to count.
        Rule PC-ALL-004 evaluates to PASS.
        """
        raw_text = "12 X 25g\nMRP Rs. 120"
        fields = extract_declarations(raw_text)

        qty = fields.get("DECLARED_NET_QUANTITY")
        assert qty is not None, "DECLARED_NET_QUANTITY must be present"
        assert qty.get("is_multipack") is True
        assert qty.get("pack_count") == 12
        assert str(qty.get("unit_net_quantity")) == "25"
        assert qty.get("unit") == "g"
        assert qty.get("derived_total_quantity") == 300

        rules = [
            {
                "rule_id": "PC-ALL-004",
                "rule_name": "Net Quantity Declaration",
                "parameter": "DECLARED_NET_QUANTITY",
                "required": True,
                "is_active": True,
            }
        ]
        results, overall = evaluate_rules(rules, fields)
        assert results[0]["status"] == "PASS"

    def test_g_rule_result_counts_consistency(self):
        """TEST G: Rule Result Counts Consistency.
        Summary counters (Passed, Failed, Review Required, N/A) must strictly equal
        the total evaluated rule rows across all evaluation paths, and rule deduplication
        guarantees no duplicate rule IDs.
        """
        sample_rules = [
            {"rule_id": f"RULE-{i:03d}", "parameter": f"PARAM_{i}", "required": True, "is_active": True}
            for i in range(1, 11)
        ]
        # Introduce a duplicate rule to test engine deduplication
        sample_rules.append(
            {"rule_id": "RULE-001", "parameter": "PARAM_1", "required": True, "is_active": True}
        )

        mock_fields = {
            "PARAM_1": {"value": "Valid 1", "confidence": 0.9},
            "PARAM_2": {"value": "Valid 2", "confidence": 0.9},
            "PARAM_3": {"value": "Valid 3", "confidence": 0.9},
            "PARAM_4": {"value": "Ambiguous 4", "status": "AMBIGUOUS", "competing_candidates": ["A", "B"]},
            "PARAM_5": {"value": "Conflicting 5", "status": "CONFLICTING_EVIDENCE", "has_conflict": True},
        }

        results, overall = evaluate_rules(sample_rules, mock_fields)
        rule_ids = [r["rule_id"] for r in results]
        assert len(rule_ids) == len(set(rule_ids)), "All evaluated rule rows must have unique rule_ids"
        assert len(results) == 10, f"Expected exactly 10 deduplicated rule rows, got {len(results)}"

        summary = calculate_rule_summary(results)
        passed = summary["passed_count"]
        failed = summary["failed_count"]
        review = summary["review_count"]
        na = summary["na_count"]

        assert passed + failed + review + na == len(results)
        assert summary["total_rules"] == len(results)

        # Verify summary counts match individual rows exactly
        row_passed = sum(1 for r in results if r["status"] == "PASS")
        row_failed = sum(1 for r in results if r["status"] == "FAIL")
        row_review = sum(1 for r in results if r["status"] in ("NOT_VERIFIABLE", "NEEDS_REVIEW", "REVIEW"))
        row_na = sum(1 for r in results if r["status"] == "NOT_APPLICABLE")

        assert passed == row_passed
        assert failed == row_failed
        assert review == row_review
        assert na == row_na

    def test_h_multi_image_conflict_scoped_review(self):
        """TEST H: Multi-Image Conflict Scoped Review.
        An ambiguous or conflicting declaration (e.g. MRP conflict) triggers NOT_VERIFIABLE
        strictly for dependent rules, while clean declarations (e.g. Net Qty) remain PASS.
        """
        mock_fields = {
            "MRP": {
                "value": "₹100.00",
                "status": "CONFLICTING_EVIDENCE",
                "has_conflict": True,
                "conflict_reason": "Image 1 declares ₹100.00 while Image 2 declares ₹120.00",
                "candidates": [
                    {"value": "₹100.00", "source": "OCR_IMAGE_1"},
                    {"value": "₹120.00", "source": "OCR_IMAGE_2"},
                ],
                "confidence": 0.85,
            },
            "DECLARED_NET_QUANTITY": {
                "value": "500 g",
                "numeric_value": 500,
                "unit": "g",
                "quantity_unit_valid": True,
                "confidence": 0.92,
            },
        }

        rules = [
            {
                "rule_id": "PC-ALL-002",
                "rule_name": "Maximum Retail Price (MRP)",
                "parameter": "MRP",
                "required": True,
                "is_active": True,
            },
            {
                "rule_id": "PC-ALL-004",
                "rule_name": "Net Quantity Declaration",
                "parameter": "DECLARED_NET_QUANTITY",
                "required": True,
                "is_active": True,
            },
        ]

        results, overall = evaluate_rules(rules, mock_fields)
        by_id = {r["rule_id"]: r for r in results}

        assert by_id["PC-ALL-002"]["status"] == "NOT_VERIFIABLE"
        assert by_id["PC-ALL-002"]["competing_evidence"] is not None
        assert by_id["PC-ALL-004"]["status"] == "PASS"

        assert overall in ("REQUIRES_REVIEW", "NOT_VERIFIABLE", "NON-COMPLIANT")
        summary = calculate_rule_summary(results)
        assert summary["review_count"] == 1
        assert summary["passed_count"] == 1
        assert summary["failed_count"] == 0
