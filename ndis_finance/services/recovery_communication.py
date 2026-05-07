import frappe
from frappe import _
from frappe.utils import add_days, flt, get_datetime, now_datetime, nowdate

from ndis_finance.services.recovery_engine import add_recovery_activity


def make_draft_id(draft_type=None):
    prefix = "NDIS-EMAIL"

    if draft_type == "Remittance Request":
        prefix = "NDIS-REM"
    elif draft_type == "Invoice Resend":
        prefix = "NDIS-INV-RESEND"
    elif draft_type == "NDIA Rejection Follow Up":
        prefix = "NDIS-REJECT-EMAIL"
    elif draft_type == "Short Payment Follow Up":
        prefix = "NDIS-SHORT-EMAIL"
    elif draft_type == "Write Off Internal Review":
        prefix = "NDIS-WO-EMAIL"

    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{timestamp}-{frappe.generate_hash(length=5).upper()}"


def safe_db_set(doctype, name, fieldname, value):
    if name and frappe.get_meta(doctype).has_field(fieldname):
        frappe.db.set_value(doctype, name, fieldname, value, update_modified=False)


def get_default_template(draft_type=None, case_type=None):
    filters = {
        "active": 1,
        "default_for_type": 1,
    }

    if draft_type:
        filters["template_type"] = draft_type

    if case_type:
        filters["case_type"] = case_type

    template = frappe.get_all(
        "NDIS Recovery Communication Template",
        filters=filters,
        fields=["name"],
        order_by="modified desc",
        limit=1,
    )

    if template:
        return template[0].name

    fallback_filters = {"active": 1}
    if draft_type:
        fallback_filters["template_type"] = draft_type

    template = frappe.get_all(
        "NDIS Recovery Communication Template",
        filters=fallback_filters,
        fields=["name"],
        order_by="modified desc",
        limit=1,
    )

    return template[0].name if template else None


def get_context(recovery_case):
    case = frappe.get_doc("NDIS Recovery Case", recovery_case)

    participant = frappe._dict()
    if case.participant and frappe.db.exists("Customer", case.participant):
        participant = frappe.get_doc("Customer", case.participant).as_dict()

    sales_invoice = frappe._dict()
    if case.sales_invoice and frappe.db.exists("Sales Invoice", case.sales_invoice):
        sales_invoice = frappe.get_doc("Sales Invoice", case.sales_invoice).as_dict()

    claim_line = frappe._dict()
    if case.claim_line and frappe.db.exists("NDIS Claim Line", case.claim_line):
        claim_line = frappe.get_doc("NDIS Claim Line", case.claim_line).as_dict()

    funding_leakage = frappe._dict()
    if case.funding_leakage and frappe.db.exists(
        "NDIS Funding Leakage Register",
        case.funding_leakage,
    ):
        funding_leakage = frappe.get_doc(
            "NDIS Funding Leakage Register",
            case.funding_leakage,
        ).as_dict()

    company = frappe._dict()
    if case.company and frappe.db.exists("Company", case.company):
        company = frappe.get_doc("Company", case.company).as_dict()

    return {
        "case": case.as_dict(),
        "participant": participant,
        "sales_invoice": sales_invoice,
        "claim_line": claim_line,
        "funding_leakage": funding_leakage,
        "company": company,
        "today": nowdate(),
    }


def infer_draft_type_from_case(case):
    if case.case_type == "Rejected Claim":
        return "NDIA Rejection Follow Up"
    if case.case_type == "Payment Shortfall":
        return "Short Payment Follow Up"
    if case.case_type == "Remittance Request":
        return "Remittance Request"
    if case.case_type == "Invoice Resend":
        return "Invoice Resend"
    if case.case_type == "Write Off Review":
        return "Write Off Internal Review"
    if case.case_type == "Plan Manager Follow Up":
        return "Plan Manager Follow Up"

    return "Plan Manager Follow Up"


@frappe.whitelist()
def preview_recovery_email(recovery_case, template=None, draft_type=None):
    if not frappe.db.exists("NDIS Recovery Case", recovery_case):
        frappe.throw(_("Recovery Case not found: {0}").format(recovery_case))

    case = frappe.get_doc("NDIS Recovery Case", recovery_case)
    draft_type = draft_type or infer_draft_type_from_case(case)
    template = template or get_default_template(draft_type=draft_type, case_type=case.case_type)

    if not template:
        frappe.throw(
            _("No active NDIS Recovery Communication Template found for {0}.").format(
                draft_type
            )
        )

    template_doc = frappe.get_doc("NDIS Recovery Communication Template", template)
    context = get_context(recovery_case)

    return {
        "recovery_case": recovery_case,
        "template": template,
        "draft_type": draft_type,
        "recipient_email": case.contact_email,
        "subject": frappe.render_template(template_doc.subject_template, context),
        "body": frappe.render_template(template_doc.body_template, context),
    }


@frappe.whitelist()
def create_recovery_email_draft(
    recovery_case,
    template=None,
    draft_type=None,
    recipient_email=None,
    cc=None,
    bcc=None,
    internal_note=None,
    next_follow_up_date=None,
):
    """
    Create a controlled NDIS recovery email draft.

    This does not send email. It only creates an internal draft record and logs
    a recovery activity.
    """

    if not frappe.db.exists("NDIS Recovery Case", recovery_case):
        frappe.throw(_("Recovery Case not found: {0}").format(recovery_case))

    case = frappe.get_doc("NDIS Recovery Case", recovery_case)
    draft_type = draft_type or infer_draft_type_from_case(case)
    template = template or get_default_template(draft_type=draft_type, case_type=case.case_type)

    if not template:
        frappe.throw(
            _("No active NDIS Recovery Communication Template found for {0}.").format(
                draft_type
            )
        )

    template_doc = frappe.get_doc("NDIS Recovery Communication Template", template)
    context = get_context(recovery_case)

    doc = frappe.new_doc("NDIS Recovery Email Draft")
    doc.draft_id = make_draft_id(draft_type)
    doc.status = "Draft"
    doc.draft_type = draft_type
    doc.template = template
    doc.recovery_case = recovery_case

    doc.participant = case.participant
    doc.sales_invoice = case.sales_invoice
    doc.claim_line = case.claim_line
    doc.funding_leakage = case.funding_leakage

    doc.recipient_email = recipient_email or case.contact_email
    doc.cc = cc
    doc.bcc = bcc
    doc.subject = frappe.render_template(template_doc.subject_template, context)
    doc.body = frappe.render_template(template_doc.body_template, context)

    doc.expected_amount = flt(case.expected_amount)
    doc.paid_amount = flt(case.paid_amount)
    doc.outstanding_amount = flt(case.outstanding_amount)

    doc.generated_on = now_datetime()
    doc.generated_by = frappe.session.user
    doc.internal_note = internal_note
    doc.insert(ignore_permissions=True)

    activity = add_recovery_activity(
        recovery_case=recovery_case,
        activity_type="Email",
        outcome="Other",
        activity_note=(
            f"Email draft created: {doc.draft_id} ({draft_type}). "
            "No email was sent automatically."
        ),
        next_follow_up_date=next_follow_up_date or add_days(nowdate(), 3),
        commit=False,
    )

    safe_db_set("NDIS Recovery Activity", activity.get("activity"), "email_draft", doc.name)

    doc.activity = activity.get("activity")
    doc.save(ignore_permissions=True)

    update_case_communication_status(
        recovery_case=recovery_case,
        draft=doc.name,
        status="Draft Created",
        next_due_date=next_follow_up_date or add_days(nowdate(), 3),
    )

    frappe.db.commit()

    return {
        "created": True,
        "email_draft": doc.name,
        "draft_id": doc.draft_id,
        "status": doc.status,
        "draft_type": doc.draft_type,
        "recipient_email": doc.recipient_email,
        "subject": doc.subject,
        "message": "Email draft created. No email was sent automatically.",
    }


def update_case_communication_status(recovery_case, draft, status, next_due_date=None):
    safe_db_set("NDIS Recovery Case", recovery_case, "last_email_draft", draft)
    safe_db_set("NDIS Recovery Case", recovery_case, "communication_status", status)
    safe_db_set("NDIS Recovery Case", recovery_case, "last_communication_on", now_datetime())
    safe_db_set("NDIS Recovery Case", recovery_case, "next_communication_due_date", next_due_date)


@frappe.whitelist()
def approve_email_draft(email_draft):
    if not frappe.db.exists("NDIS Recovery Email Draft", email_draft):
        frappe.throw(_("Email Draft not found: {0}").format(email_draft))

    doc = frappe.get_doc("NDIS Recovery Email Draft", email_draft)

    if doc.status != "Draft":
        frappe.throw(_("Only Draft email records can be approved."))

    doc.status = "Approved"
    doc.approved_on = now_datetime()
    doc.approved_by = frappe.session.user
    doc.save(ignore_permissions=True)

    add_recovery_activity(
        recovery_case=doc.recovery_case,
        activity_type="Email",
        outcome="Other",
        activity_note=(
            f"Email draft approved: {doc.draft_id}. "
            "No email was sent automatically."
        ),
        next_follow_up_date=get_case_follow_up_date(doc.recovery_case),
        commit=False,
    )

    update_case_communication_status(
        recovery_case=doc.recovery_case,
        draft=doc.name,
        status="Approved",
        next_due_date=None,
    )

    frappe.db.commit()

    return {
        "email_draft": doc.name,
        "status": doc.status,
        "message": "Email draft approved. No email was sent automatically.",
    }


@frappe.whitelist()
def mark_email_draft_sent_manually(email_draft, note=None):
    """
    Mark an email draft as sent manually.

    This does not send email.
    """

    if not frappe.db.exists("NDIS Recovery Email Draft", email_draft):
        frappe.throw(_("Email Draft not found: {0}").format(email_draft))

    doc = frappe.get_doc("NDIS Recovery Email Draft", email_draft)

    if doc.status not in ["Draft", "Approved"]:
        frappe.throw(_("Only Draft or Approved email records can be marked as sent manually."))

    doc.status = "Sent Manually"
    doc.sent_manually_on = now_datetime()
    doc.sent_manually_by = frappe.session.user
    if note:
        doc.internal_note = note
    doc.save(ignore_permissions=True)

    add_recovery_activity(
        recovery_case=doc.recovery_case,
        activity_type="Email",
        outcome="Awaiting Response",
        activity_note=note or f"Email draft marked as sent manually: {doc.draft_id}.",
        next_follow_up_date=add_days(nowdate(), 3),
        commit=False,
    )

    update_case_communication_status(
        recovery_case=doc.recovery_case,
        draft=doc.name,
        status="Sent Manually",
        next_due_date=add_days(nowdate(), 3),
    )

    frappe.db.commit()

    return {
        "email_draft": doc.name,
        "status": doc.status,
        "message": "Email draft marked as sent manually. No email was sent by the system.",
    }


@frappe.whitelist()
def cancel_email_draft(email_draft, reason=None):
    if not frappe.db.exists("NDIS Recovery Email Draft", email_draft):
        frappe.throw(_("Email Draft not found: {0}").format(email_draft))

    doc = frappe.get_doc("NDIS Recovery Email Draft", email_draft)

    if doc.status == "Sent Manually":
        frappe.throw(_("A draft already marked Sent Manually cannot be cancelled."))

    doc.status = "Cancelled"
    if reason:
        doc.internal_note = reason
    doc.save(ignore_permissions=True)

    add_recovery_activity(
        recovery_case=doc.recovery_case,
        activity_type="Note",
        outcome="Other",
        activity_note=reason or f"Email draft cancelled: {doc.draft_id}.",
        next_follow_up_date=get_case_follow_up_date(doc.recovery_case),
        commit=False,
    )

    update_case_communication_status(
        recovery_case=doc.recovery_case,
        draft=doc.name,
        status="Cancelled",
        next_due_date=None,
    )

    frappe.db.commit()

    return {
        "email_draft": doc.name,
        "status": doc.status,
    }


@frappe.whitelist()
def quick_email_draft_summary(limit=20):
    return frappe.get_all(
        "NDIS Recovery Email Draft",
        fields=[
            "name",
            "draft_id",
            "status",
            "draft_type",
            "recovery_case",
            "participant",
            "sales_invoice",
            "recipient_email",
            "subject",
            "expected_amount",
            "paid_amount",
            "outstanding_amount",
            "generated_on",
            "generated_by",
            "approved_on",
            "sent_manually_on",
        ],
        order_by="modified desc",
        limit=int(limit or 20),
    )


def get_case_follow_up_date(recovery_case):
    return frappe.db.get_value("NDIS Recovery Case", recovery_case, "next_follow_up_date")
