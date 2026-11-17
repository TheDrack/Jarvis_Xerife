from __future__ import annotations

import sqlite3

import pytest

from app.application.prospecting.outreach import (
    Channel,
    ContactAuthorization,
    OutreachService,
    SQLiteOutreachStore,
)


class FakeTransport:
    def __init__(self, result=None):
        self.calls = []
        self.result = result or {"accepted": True, "provider_id": "msg-1"}

    def send(self, *, destination, subject, body, metadata):
        self.calls.append((destination, subject, body, metadata))
        return self.result


def service(tmp_path, transports=None):
    store = SQLiteOutreachStore(tmp_path / "outreach.sqlite3")
    return OutreachService(store, transports=transports or {}), store


def authorization():
    return ContactAuthorization(
        basis="legitimate_interest_reviewed",
        evidence_ref="review:case-42",
        reviewed_by="operator",
    )


def test_plan_is_durable_and_does_not_send_before_explicit_approval(tmp_path):
    outreach, store = service(tmp_path, {Channel.EMAIL: FakeTransport()})

    result = outreach.create_plan(
        company_id="12345678000190",
        channel=Channel.EMAIL,
        destination="sales@example.com",
        subject="Apresentação comercial",
        body="Olá, gostaria de apresentar nossos serviços.",
        campaign_id="campaign-1",
        authorization=authorization(),
    )

    assert result.status == "pending_approval"
    assert outreach.get_plan(result.plan_id).status == "pending_approval"
    assert store.list_events(result.plan_id)[-1]["event"] == "plan_created"


def test_approval_and_dispatch_send_once_and_replay_is_idempotent(tmp_path):
    transport = FakeTransport()
    outreach, _ = service(tmp_path, {Channel.EMAIL: transport})
    plan = outreach.create_plan(
        company_id="12345678000190",
        channel=Channel.EMAIL,
        destination="sales@example.com",
        subject="Apresentação",
        body="Mensagem inicial",
        campaign_id="campaign-1",
        authorization=authorization(),
    )

    approved = outreach.approve_plan(plan.plan_id, approved_by="operator")
    sent = outreach.dispatch(plan.plan_id, idempotency_key="send-123")
    replay = outreach.dispatch(plan.plan_id, idempotency_key="send-123")

    assert approved.status == "approved"
    assert sent.status == "sent"
    assert replay.status == "sent"
    assert len(transport.calls) == 1


def test_duplicate_company_channel_destination_and_campaign_is_rejected(tmp_path):
    outreach, _ = service(tmp_path)
    values = dict(
        company_id="12345678000190",
        channel=Channel.WHATSAPP,
        destination="+5548999999999",
        subject=None,
        body="Olá",
        campaign_id="campaign-1",
        authorization=authorization(),
    )
    outreach.create_plan(**values)

    with pytest.raises(ValueError, match="duplicate_outreach"):
        outreach.create_plan(**values)


def test_do_not_contact_blocks_existing_pending_plan(tmp_path):
    transport = FakeTransport()
    outreach, _ = service(tmp_path, {Channel.EMAIL: transport})
    plan = outreach.create_plan(
        company_id="12345678000190",
        channel=Channel.EMAIL,
        destination="sales@example.com",
        subject="Apresentação",
        body="Mensagem",
        campaign_id="campaign-1",
        authorization=authorization(),
    )
    outreach.block_contact(
        company_id="12345678000190",
        channel=Channel.EMAIL,
        destination="sales@example.com",
        reason="recipient_requested_stop",
        recorded_by="operator",
    )

    with pytest.raises(PermissionError, match="do_not_contact"):
        outreach.approve_plan(plan.plan_id, approved_by="operator")
    assert transport.calls == []


def test_dispatch_requires_approval_and_configured_transport(tmp_path):
    outreach, _ = service(tmp_path)
    plan = outreach.create_plan(
        company_id="12345678000190",
        channel=Channel.PHONE,
        destination="+5548999999999",
        subject=None,
        body="Solicitar retorno comercial",
        campaign_id="campaign-1",
        authorization=authorization(),
    )

    with pytest.raises(PermissionError, match="approval_required"):
        outreach.dispatch(plan.plan_id, idempotency_key="send-1")

    outreach.approve_plan(plan.plan_id, approved_by="operator")
    with pytest.raises(LookupError, match="transport_unavailable"):
        outreach.dispatch(plan.plan_id, idempotency_key="send-1")


def test_authorization_requires_traceable_basis_and_reviewer(tmp_path):
    outreach, _ = service(tmp_path)
    with pytest.raises(ValueError, match="authorization_evidence_required"):
        outreach.create_plan(
            company_id="12345678000190",
            channel=Channel.EMAIL,
            destination="sales@example.com",
            subject="Apresentação",
            body="Mensagem",
            campaign_id="campaign-1",
            authorization=ContactAuthorization(
                basis="legitimate_interest_reviewed", evidence_ref="", reviewed_by=""
            ),
        )


def test_provider_failure_is_audited_and_does_not_mark_message_sent(tmp_path):
    transport = FakeTransport({"accepted": False, "error": "provider_rejected"})
    outreach, store = service(tmp_path, {Channel.EMAIL: transport})
    plan = outreach.create_plan(
        company_id="12345678000190",
        channel=Channel.EMAIL,
        destination="sales@example.com",
        subject="Apresentação",
        body="Mensagem",
        campaign_id="campaign-1",
        authorization=authorization(),
    )
    outreach.approve_plan(plan.plan_id, approved_by="operator")

    with pytest.raises(RuntimeError, match="provider_rejected"):
        outreach.dispatch(plan.plan_id, idempotency_key="send-1")

    assert outreach.get_plan(plan.plan_id).status == "failed"
    assert store.list_events(plan.plan_id)[-1]["event"] == "delivery_failed"


def test_phone_and_web_form_are_distinct_channels(tmp_path):
    outreach, _ = service(tmp_path)
    phone = outreach.create_plan(
        company_id="12345678000190",
        channel=Channel.PHONE,
        destination="+5548999999999",
        subject=None,
        body="Script de ligação",
        campaign_id="campaign-1",
        authorization=authorization(),
    )
    form = outreach.create_plan(
        company_id="12345678000191",
        channel=Channel.WEB_FORM,
        destination="https://example.com/contact",
        subject=None,
        body="Mensagem institucional",
        campaign_id="campaign-1",
        authorization=authorization(),
    )

    assert phone.channel == Channel.PHONE
    assert form.channel == Channel.WEB_FORM


def test_company_wide_do_not_contact_blocks_every_channel(tmp_path):
    transport = FakeTransport()
    outreach, _ = service(tmp_path, {Channel.EMAIL: transport})
    plan = outreach.create_plan(
        company_id="12345678000190",
        channel=Channel.EMAIL,
        destination="sales@example.com",
        subject="Apresentação",
        body="Mensagem",
        campaign_id="campaign-1",
        authorization=authorization(),
    )

    outreach.block_contact(
        company_id="12345678000190",
        channel=None,
        destination=None,
        reason="recipient_requested_stop",
        recorded_by="operator",
    )

    with pytest.raises(PermissionError, match="do_not_contact"):
        outreach.approve_plan(plan.plan_id, approved_by="operator")

    assert transport.calls == []


def test_form_destination_must_be_https_and_email_requires_subject(tmp_path):
    outreach, _ = service(tmp_path)

    with pytest.raises(ValueError, match="web_form_requires_https_url"):
        outreach.create_plan(
            company_id="12345678000190",
            channel=Channel.WEB_FORM,
            destination="http://example.com/contact",
            subject=None,
            body="Mensagem",
            campaign_id="campaign-1",
            authorization=authorization(),
        )

    with pytest.raises(ValueError, match="email_subject_required"):
        outreach.create_plan(
            company_id="12345678000190",
            channel=Channel.EMAIL,
            destination="sales@example.com",
            subject=None,
            body="Mensagem",
            campaign_id="campaign-2",
            authorization=authorization(),
        )
