"""Preview execution allowlist rejects queries, unsafe functions and windows."""

import pytest

from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.metric_query import check_ast, parse_expression


@pytest.mark.parametrize(
    "text",
    [
        "SUM(x)",
        "COUNT(DISTINCT x)",
        "SUM(CASE WHEN x > 0 THEN x ELSE 0 END)",
        "SUM(x)/NULLIF(COUNT(*),0)",
    ],
)
def test_allowed_aggregate_scalar_combinations(text):
    check_ast(parse_expression(text, ""), aggregate=True)


@pytest.mark.parametrize(
    "text",
    [
        "(SELECT SUM(x) FROM secret)",
        "pg_sleep(10)",
        "SUM(x) OVER ()",
        "SUM(SUM(x))",
        "x+SUM(x)",
    ],
)
def test_ast_rejects_unsafe_or_out_of_scope_expressions(text):
    with pytest.raises(ServiceError):
        check_ast(parse_expression(text, ""), aggregate=True)
