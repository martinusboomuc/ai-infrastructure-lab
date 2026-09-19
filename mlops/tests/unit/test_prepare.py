import pandas as pd

from bankml.features.credit.prepare import capture_categories, feature_columns, prepare_features


def test_feature_columns_excludes_bookkeeping_and_fair_lending_columns():
    df = pd.DataFrame(
        columns=[
            "SK_ID_CURR",
            "TARGET",
            "APPLICATION_DATE",
            "SPLIT",
            "IS_MATURE",
            "CODE_GENDER",
            "AMT_INCOME_TOTAL",
            "BUREAU_COUNT",
        ]
    )
    assert feature_columns(df) == ["AMT_INCOME_TOTAL", "BUREAU_COUNT"]


def test_prepare_features_coerces_object_columns_to_category():
    df = pd.DataFrame({"NAME_EDUCATION_TYPE": ["Higher education"], "AMT_CREDIT": [500000.0]})
    X = prepare_features(df, ["NAME_EDUCATION_TYPE", "AMT_CREDIT"])
    assert str(X["NAME_EDUCATION_TYPE"].dtype) == "category"
    assert X["AMT_CREDIT"].dtype == df["AMT_CREDIT"].dtype


def test_capture_categories_finds_every_level_across_the_given_rows():
    df = pd.DataFrame({"NAME_EDUCATION_TYPE": ["Higher education", "Secondary", None]})
    assert capture_categories(df, ["NAME_EDUCATION_TYPE"]) == {
        "NAME_EDUCATION_TYPE": ["Higher education", "Secondary"]
    }


def test_prepare_features_applies_captured_categories_even_when_a_row_lacks_them():
    # The single-row-serving-request case this whole mechanism exists for: this row only ever
    # sees one category value, but the model was fit on the full training-time level set.
    categories = {"NAME_EDUCATION_TYPE": ["Academic degree", "Higher education", "Secondary"]}
    df = pd.DataFrame({"NAME_EDUCATION_TYPE": ["Higher education"]})

    X = prepare_features(df, ["NAME_EDUCATION_TYPE"], categories=categories)

    assert list(X["NAME_EDUCATION_TYPE"].cat.categories) == categories["NAME_EDUCATION_TYPE"]


def test_prepare_features_does_not_categorize_a_column_absent_from_captured_categories():
    # A *_MEAN aggregate column that's entirely NaN for one applicant (no history in that
    # table — the common case for a request-time-only applicant) can come back object-dtyped
    # from the join, not float64. With categories supplied, that column must stay untouched —
    # not misdetected as categorical by its own (accidental) dtype. See capture_categories's
    # docstring for why this used to change how many columns LightGBM saw as categorical.
    categories = {"NAME_EDUCATION_TYPE": ["Higher education"]}
    df = pd.DataFrame(
        {"NAME_EDUCATION_TYPE": ["Higher education"], "BUREAU_AMT_CREDIT_SUM_MEAN": [None]}
    )
    df["BUREAU_AMT_CREDIT_SUM_MEAN"] = df["BUREAU_AMT_CREDIT_SUM_MEAN"].astype(object)

    X = prepare_features(
        df, ["NAME_EDUCATION_TYPE", "BUREAU_AMT_CREDIT_SUM_MEAN"], categories=categories
    )

    assert str(X["NAME_EDUCATION_TYPE"].dtype) == "category"
    assert str(X["BUREAU_AMT_CREDIT_SUM_MEAN"].dtype) != "category"
