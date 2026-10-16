from io import BytesIO

import pandas as pd

from services.upload_analysis import profile_table, read_table, time_series


def test_profiles_common_business_fields_and_quality():
    frame = pd.DataFrame({
        "order_date": ["2025-01-10", "2025-02-10", "2025-02-10"],
        "sales": [10, 20, 20],
        "customer_id": ["c1", "c2", "c2"],
        "product": ["a", "b", "b"],
    })
    result = profile_table(frame)
    assert (result["date"], result["sales"], result["customer"], result["product"]) == (
        "order_date", "sales", "customer_id", "product"
    )
    assert result["rows"] == 3
    assert result["duplicates"] == 1
    assert time_series(result)["sales"].tolist() == [10, 40]


def test_reads_csv_payload():
    frame = read_table("sample.csv", b"sales,product\n12,book\n")
    assert frame.to_dict("records") == [{"sales": 12, "product": "book"}]


def test_empty_data_is_rejected():
    import pytest

    with pytest.raises(ValueError, match="no data"):
        profile_table(pd.DataFrame())
