from reciepe_rec.ml_predictor import passes


def test_ml_pass_rule_requires_both_rates_to_be_strictly_below_ten_percent():
    actual = {f"I{index}" for index in range(10)}

    assert passes(actual, actual)
    assert not passes(actual - {"I0"}, actual)
    assert not passes((actual - {"I0"}) | {"EXTRA"}, actual)
