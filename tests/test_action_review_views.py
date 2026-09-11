import json

import pytest

from intentfence.action_review_views import bucket_request_view, missing_email_body_view


def candidate():
    return {"tool": "memory.bucket_policy_proposal", "arguments": {
        "bucket": "fixture-bucket", "effect": "Allow", "principal": "*",
        "action": "s3:GetObject", "resource": "arn:aws:s3:::fixture-bucket/*"}}


def test_policy_wrap_preserves_statement_without_invented_version():
    result = bucket_request_view(candidate())
    policy = json.loads(result["request_parameters"]["Policy"])
    assert policy == {"Statement": [{"Effect": "Allow", "Principal": "*",
        "Action": "s3:GetObject", "Resource": "arn:aws:s3:::fixture-bucket/*"}]}
    assert not result["executed"] and not result["effective_access_verified"]


@pytest.mark.parametrize("key,value", [("resource", "arn:aws:s3:::other/*"),
                                     ("action", "s3:*"), ("principal", "account")])
def test_unsupported_semantics_are_rejected(key, value):
    action = candidate()
    action["arguments"][key] = value
    with pytest.raises(ValueError):
        bucket_request_view(action)


def test_clarification_does_not_invent_body_or_ignore_other_issues():
    action = {"tool": "memory.clarification", "arguments": {"issues": ["missing:body"]}}
    result = missing_email_body_view(action)
    assert "email body" in result["message"] and not result["email_sent"]
    action["arguments"]["issues"].append("authorization_unknown:to[0]")
    with pytest.raises(ValueError):
        missing_email_body_view(action)
