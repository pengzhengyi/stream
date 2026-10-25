"""Smart-playlist rules as stored and sent: versioned JSON, read into the domain's rules."""

import json

import pytest

from medleyplay.application.rule_schema import MAX_CONDITIONS, read_rules, rules_document
from medleyplay.domain.errors import InvalidInputError
from medleyplay.domain.rules import Added, Favorite, Kind, Match, Rating, Rules, Text

FAVORITES_ADDED_THIS_MONTH = """
{
  "version": 1,
  "match": "all",
  "conditions": [
    { "field": "favorite", "op": "is", "value": true },
    { "field": "rating", "op": "at_least", "value": 4 },
    { "field": "rating", "op": "unrated" },
    { "field": "artist", "op": "contains", "value": "周杰伦" },
    { "field": "added", "op": "within_days", "value": 30 },
    { "field": "source_kind", "op": "is", "value": "bilibili" }
  ]
}
"""


def test_a_document_reads_as_the_rules_it_spells_out() -> None:
    rules = read_rules(json.loads(FAVORITES_ADDED_THIS_MONTH))

    assert rules == Rules(
        Match.ALL,
        (
            Favorite(value=True),
            Rating("at_least", 4),
            Rating("unrated"),
            Text("artist", "contains", "周杰伦"),
            Added("within_days", 30),
            Kind("bilibili"),
        ),
    )


def test_rules_written_back_read_as_the_same_document() -> None:
    document = json.loads(FAVORITES_ADDED_THIS_MONTH)

    assert rules_document(read_rules(document)) == document


@pytest.mark.parametrize(
    ("change", "why"),
    [
        ({"version": 2}, "version 2"),
        ({"match": "most"}, "match"),
        ({"conditions": []}, "conditions"),
        ({"conditions": [{"field": "mood", "op": "is", "value": "calm"}]}, "mood"),
        ({"conditions": [{"field": "rating", "op": "at_least", "value": 6}]}, "rating"),
        ({"conditions": [{"field": "rating", "op": "at_least"}]}, "rating"),
        ({"conditions": [{"field": "rating", "op": "unrated", "value": 3}]}, "rating"),
        ({"conditions": [{"field": "added", "op": "within_days", "value": 0}]}, "added"),
        ({"conditions": [{"field": "title", "op": "is", "value": ""}]}, "title"),
        ({"conditions": [{"field": "favorite", "op": "is", "value": True, "x": 1}]}, "x"),
    ],
)
def test_a_document_the_schema_does_not_allow_is_refused_saying_where(
    change: dict[str, object], why: str
) -> None:
    document = {**json.loads(FAVORITES_ADDED_THIS_MONTH), **change}

    with pytest.raises(InvalidInputError, match=why):
        read_rules(document)


def test_more_conditions_than_the_limit_are_refused() -> None:
    favorite = {"field": "favorite", "op": "is", "value": True}
    document = {"version": 1, "match": "any", "conditions": [favorite] * (MAX_CONDITIONS + 1)}

    with pytest.raises(InvalidInputError, match="conditions"):
        read_rules(document)
