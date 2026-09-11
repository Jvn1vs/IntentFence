"""Inspectable offline representations, never dispatched or counted as new actions."""
from __future__ import annotations

import json
from typing import Literal

from pydantic import model_validator

from intentfence.offline_actions import StrictModel, Text


class BucketStatementFields(StrictModel):
    bucket: Text
    effect: Literal["Allow", "Deny"]
    principal: Literal["*"]
    action: Literal["s3:GetObject"]
    resource: Text

    @model_validator(mode="after")
    def object_scope(self) -> BucketStatementFields:
        if self.resource != f"arn:aws:s3:::{self.bucket}/*":
            raise ValueError("only an exact bucket-wide object resource is supported")
        return self


def bucket_request_view(candidate: dict) -> dict:
    if set(candidate) != {"tool", "arguments"} or candidate["tool"] != "memory.bucket_policy_proposal":
        raise ValueError("unsupported candidate")
    fields = BucketStatementFields.model_validate(candidate["arguments"])
    policy = {"Statement": [{"Effect": fields.effect, "Principal": fields.principal,
                             "Action": fields.action, "Resource": fields.resource}]}
    return {"operation": "s3api.put-bucket-policy", "request_parameters": {
        "Bucket": fields.bucket, "Policy": json.dumps(policy, separators=(",", ":"))},
        "scope": "offline_request_shape_only", "executed": False,
        "service_acceptance_verified": False, "effective_access_verified": False}


def missing_email_body_view(candidate: dict) -> dict:
    if candidate != {"tool": "memory.clarification", "arguments": {"issues": ["missing:body"]}}:
        raise ValueError("only the single missing email body issue is supported")
    return {"message": "Please provide the email body you want to send.",
            "issue_codes": ["missing:body"], "text_provenance": "deterministic_engineering_renderer",
            "sent_to_user": False, "email_sent": False}
