from etl.profile import build_report, infer_type
import pandas as pd

from tests.conftest import SAMPLE_DIR


def test_profile_report_on_sample():
    report = build_report(SAMPLE_DIR)
    assert "| order_items | `order_id, order_item_id` | 6 | 0 | evet |" in report
    assert "| customers | `customer_unique_id` | 5 | 1 | hayır |" in report
    assert "| order_reviews | `review_id` | 5 | 1 | hayır |" in report
    assert "| category_translation | `product_category_name_translation.csv` | 2 | 2 | var |" in report
    assert "çevirisi olmayan kategori | 1: pc_gamer |" in report


def test_infer_type_keeps_leading_zero_codes_as_text():
    assert infer_type(pd.Series(["01001", "20040"])).startswith("text")
    assert infer_type(pd.Series(["1", "21"])) == "integer"
    assert infer_type(pd.Series(["0.85", "6735.0"])).startswith("decimal")
