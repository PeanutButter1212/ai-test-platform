"""v2 test format: tests are data, not code.

The LLM fills in these models; only our engine executes them. Every check
cites the rule it comes from, so each expectation is traceable to the spec.
"""

from typing import Literal

from pydantic import BaseModel, Field


class Body(BaseModel):
    """Request body. Limited to the fields the shop API accepts."""
    product_id: int | None = None
    qty: int | None = None
    code: str | None = None


class Check(BaseModel):
    field: str = Field(description="Path into the JSON response, e.g. 'total', 'detail.code', "
                                   "'items.0.qty', or '[id=5].stock' to pick from a list")
    op: Literal["equals", "not_equals", "contains", "length"]
    value: str = Field(description="Expected value written as a string, e.g. '10.00', '409', 'SAVE10'")
    rule: str = Field(description="ID of the rule this expectation comes from, e.g. 'R1'")
    why: str = Field(description="One sentence: how the rule implies this value")


class Step(BaseModel):
    method: Literal["GET", "POST", "PATCH", "DELETE"]
    path: str = Field(description="API path; use {cart} for the cart id saved earlier")
    body: Body | None = None
    save_id_as: str | None = Field(None, description="Save response 'id' under this name, e.g. 'cart'")
    expect_status: int | None = None
    checks: list[Check] = []


class TestCase(BaseModel):
    id: str = Field(description="Unique id like 'R1-02'")
    rule: str = Field(description="Main rule under test, e.g. 'R1'")
    kind: Literal["normal", "boundary", "error"]
    title: str
    steps: list[Step]


class TestSuite(BaseModel):
    tests: list[TestCase]
