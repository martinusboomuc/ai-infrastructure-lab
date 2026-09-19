"""Training-vs-serving feature parity (Phase 4 exit criterion; ADR-0009).

Builds SK_ID_CURR=1's features twice: once through the batch training path (the synthetic
per-applicant anchor, the full multi-applicant tables), once through the single-request serving
path (that one applicant's own historical rows only, `application_dates` set to their real
`APPLICATION_DATE` instead of a freshly computed anchor). `assemble_features` is the same
function both paths call — this is the concrete proof they actually share it, not just a claim.
"""

from __future__ import annotations

import pandas as pd

from bankml.features.credit.anchor import compute_application_dates
from bankml.features.credit.pipeline import assemble_features
from tests.fixtures.credit.leakage_fixture import CONFIG, raw_tables


def test_serving_path_reproduces_the_batch_path_for_one_applicant():
    tables = raw_tables()
    anchor = CONFIG["synthetic_anchor"]
    application_dates = compute_application_dates(
        tables["application_train"], anchor["start"], anchor["end"]
    )

    batch_features = assemble_features(tables, application_dates)
    expected = batch_features[batch_features["SK_ID_CURR"] == 1].reset_index(drop=True)

    applicant_id = 1
    decision_date = application_dates.loc[applicant_id]
    single_applicant_tables = {
        "application_train": tables["application_train"][
            tables["application_train"]["SK_ID_CURR"] == applicant_id
        ],
        "bureau": tables["bureau"][tables["bureau"]["SK_ID_CURR"] == applicant_id],
        "previous_application": tables["previous_application"][
            tables["previous_application"]["SK_ID_CURR"] == applicant_id
        ],
        "POS_CASH_balance": tables["POS_CASH_balance"][
            tables["POS_CASH_balance"]["SK_ID_CURR"] == applicant_id
        ],
        "installments_payments": tables["installments_payments"][
            tables["installments_payments"]["SK_ID_CURR"] == applicant_id
        ],
        "credit_card_balance": tables["credit_card_balance"][
            tables["credit_card_balance"]["SK_ID_CURR"] == applicant_id
        ],
    }
    applicant_bureau_ids = single_applicant_tables["bureau"]["SK_ID_BUREAU"]
    single_applicant_tables["bureau_balance"] = tables["bureau_balance"][
        tables["bureau_balance"]["SK_ID_BUREAU"].isin(applicant_bureau_ids)
    ]

    serving_application_dates = pd.Series({applicant_id: decision_date})
    serving_application_dates.index.name = "SK_ID_CURR"

    actual = assemble_features(single_applicant_tables, serving_application_dates)

    pd.testing.assert_frame_equal(expected, actual)
