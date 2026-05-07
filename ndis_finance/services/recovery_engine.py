import frappe
from frappe import _
from frappe.utils import add_days, flt, now_datetime, nowdate

from ndis_finance.services.permissions import assert_action


OPEN_CASE_STATUSES = ["Open", "In Follow Up", "Waiting For Response", "Escalated"]


def make_case_id(case_type=None):
    prefix = "NDIS-REC"

    if case_type == "Rejected Claim":
        prefix = "NDIS-REJECT"
    elif case_type == "Payment Shortfall":
        prefix = "NDIS-SHORT"
    elif case_type == "Invoice Overdue":
        prefix = "NDIS-OD"
    elif case_type == "Plan Manager Follow Up":
        prefix = "NDIS-PM-FU"
    elif case_type == "NDIA Follow Up":
        prefix = "NDIS-NDIA-FU"

    timestamp = now_datetime().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{timestamp}-{frappe.generate_hash(length=5).upper()}"


def make_activity_id():
    timestamp = now_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-REC-ACT-{timestamp}-{frappe.generate_hash(length=5).upper()}"


def safe_db_set(doctype, name, fieldname, value):
    if frappe.get_meta(doctype).has_field(fieldname):
        frappe.db.set_value(doctype, name, fieldname, value, update_modified=False)


def get_open_case(filters):
    filters = dict(filters)
    filters["status"] = ["in", OPEN_CASE_STATUSES]

    existing = frappe.get_all(
        "NDIS Recovery Case",
        filters=filters,
        fields=["name"],
        order_by="modified desc",
        limit=1,
    )

    return existing[0].name if existing else None


def priority_from_amount(amount):
    amount = flt(amount)

    if amount >= 1000:
        return "Critical"
    if amount >= 250:
        return "High"
    if amount >= 50:
        return "Medium"

    return "Low"


def case_type_from_leakage(leakage_type):
    if leakage_type == "Rejected Claim":
        return "Rejected Claim"
    if leakage_type == "Payment Shortfall":
        return "Payment Shortfall"
    if leakage_type == "Underbilling":
        return "Invoice Overdue"
    return "Other"


def can_create_recovery_case_without_user_action_check():
    return bool(getattr(frappe.flags, "ndis_allow_recovery_case_creation", False))


@frappe.whitelist()
def create_recovery_case_from_leakage(funding_leakage, assigned_to=None, due_days=7):
    """
    Create one recovery case from a funding leakage record.

    Idempotent:
    - If an open recovery case already exists for this leakage, it returns that case.
    """

    if not can_create_recovery_case_without_user_action_check():
        assert_action("create_recovery_case")

    if not frappe.db.exists("NDIS Funding Leakage Register", funding_leakage):
        frappe.throw(_("Funding Leakage record not found: {0}").format(funding_leakage))

    leakage = frappe.get_doc("NDIS Funding Leakage Register", funding_leakage)

    existing = get_open_case({"funding_leakage": leakage.name})
    if existing:
        return {
            "created": False,
            "recovery_case": existing,
            "message": "Open recovery case already exists for this funding leakage.",
        }

    claim_line = None
    if getattr(leakage, "claim_line", None) and frappe.db.exists(
        "NDIS Claim Line", leakage.claim_line
    ):
        claim_line = frappe.get_doc("NDIS Claim Line", leakage.claim_line)

    case_type = case_type_from_leakage(leakage.leakage_type)
    assigned_to = assigned_to or getattr(leakage, "assigned_to", None) or frappe.session.user

    case = frappe.new_doc("NDIS Recovery Case")
    case.case_id = make_case_id(case_type)
    case.case_type = case_type
    case.status = "Open"
    case.priority = priority_from_amount(leakage.variance_amount)
    case.assigned_to = assigned_to

    case.participant = leakage.participant
    case.house = leakage.house
    case.funding_leakage = leakage.name
    case.claim_batch = getattr(leakage, "claim_batch", None)
    case.claim_line = getattr(leakage, "claim_line", None)
    case.payment_reconciliation_batch = getattr(
        leakage, "payment_reconciliation_batch", None
    )
    case.payment_reconciliation_line = getattr(leakage, "payment_reconciliation_line", None)
    case.sales_invoice = getattr(leakage, "sales_invoice", None)
    case.sales_invoice_item = getattr(leakage, "sales_invoice_item", None)

    if claim_line:
        case.company = claim_line.company
        case.funding_source = claim_line.funding_source
        case.expected_amount = flt(claim_line.claim_amount)
        case.paid_amount = flt(claim_line.paid_amount)
        case.outstanding_amount = flt(claim_line.shortfall_amount)
    else:
        case.expected_amount = flt(leakage.expected_amount)
        case.paid_amount = flt(leakage.actual_amount)
        case.outstanding_amount = flt(leakage.variance_amount)

    case.case_opened_on = now_datetime()
    case.next_follow_up_date = add_days(nowdate(), int(due_days or 7))
    case.case_summary = build_case_summary_from_leakage(leakage, claim_line)

    case.insert(ignore_permissions=True)

    link_recovery_case_to_sources(case)
    log_recovery_activity(
        recovery_case=case.name,
        activity_type="Note",
        outcome="Other",
        activity_note="Recovery case created from funding leakage.",
        next_follow_up_date=case.next_follow_up_date,
        commit=False,
    )

    frappe.db.commit()

    return {
        "created": True,
        "recovery_case": case.name,
        "case_id": case.case_id,
        "case_type": case.case_type,
        "priority": case.priority,
        "outstanding_amount": flt(case.outstanding_amount),
        "next_follow_up_date": case.next_follow_up_date,
    }


def build_case_summary_from_leakage(leakage, claim_line=None):
    parts = [
        f"Leakage Type: {leakage.leakage_type}",
        f"Expected: {flt(leakage.expected_amount):.2f}",
        f"Actual: {flt(leakage.actual_amount):.2f}",
        f"Variance: {flt(leakage.variance_amount):.2f}",
    ]

    if claim_line:
        parts.append(f"Claim Line: {claim_line.name}")
        parts.append(f"Sales Invoice: {claim_line.sales_invoice}")
        parts.append(f"Support Item: {claim_line.support_item_number}")

    if leakage.resolution_note:
        parts.append(f"Reason/Note: {leakage.resolution_note}")

    return " | ".join(parts)


def link_recovery_case_to_sources(case):
    if case.funding_leakage:
        safe_db_set("NDIS Funding Leakage Register", case.funding_leakage, "recovery_case", case.name)
        safe_db_set("NDIS Funding Leakage Register", case.funding_leakage, "recovery_status", "Open")
        safe_db_set("NDIS Funding Leakage Register", case.funding_leakage, "assigned_to", case.assigned_to)
        safe_db_set(
            "NDIS Funding Leakage Register",
            case.funding_leakage,
            "follow_up_due_date",
            case.next_follow_up_date,
        )

    if case.claim_line:
        safe_db_set("NDIS Claim Line", case.claim_line, "recovery_case", case.name)
        safe_db_set("NDIS Claim Line", case.claim_line, "recovery_status", "Open")
        safe_db_set("NDIS Claim Line", case.claim_line, "follow_up_due_date", case.next_follow_up_date)

    if case.payment_reconciliation_line:
        safe_db_set(
            "NDIS Payment Reconciliation Line",
            case.payment_reconciliation_line,
            "recovery_case",
            case.name,
        )

    if case.sales_invoice:
        refresh_invoice_recovery_status(case.sales_invoice)


@frappe.whitelist()
def create_recovery_cases_from_open_leakages(limit=50, assigned_to=None):
    """
    Bulk-create recovery cases from open leakage records.
    """

    if not can_create_recovery_case_without_user_action_check():
        assert_action("create_recovery_case")

    leakages = frappe.get_all(
        "NDIS Funding Leakage Register",
        filters={
            "status": ["in", ["Open", "In Review"]],
        },
        fields=["name"],
        order_by="modified asc",
        limit=int(limit or 50),
    )

    results = []

    for leakage in leakages:
        result = create_recovery_case_from_leakage(
            funding_leakage=leakage.name,
            assigned_to=assigned_to,
            due_days=7,
        )
        results.append(result)

    return {
        "processed": len(results),
        "created": len([r for r in results if r.get("created")]),
        "already_existing": len([r for r in results if not r.get("created")]),
        "results": results[:20],
    }


def log_recovery_activity(
    recovery_case,
    activity_type="Note",
    outcome=None,
    activity_note=None,
    next_follow_up_date=None,
    attachment=None,
    commit=True,
):
    if not frappe.db.exists("NDIS Recovery Case", recovery_case):
        frappe.throw(_("Recovery Case not found: {0}").format(recovery_case))

    case = frappe.get_doc("NDIS Recovery Case", recovery_case)

    activity = frappe.new_doc("NDIS Recovery Activity")
    activity.name = make_activity_id()
    activity.flags.name_set = True
    activity.recovery_case = recovery_case
    activity.activity_datetime = now_datetime()
    activity.activity_type = activity_type
    activity.performed_by = frappe.session.user
    activity.outcome = outcome
    activity.next_follow_up_date = next_follow_up_date
    activity.activity_note = activity_note
    activity.attachment = attachment
    activity.insert(ignore_permissions=True)

    new_status = case.status

    if activity_type in ["Call", "Email", "SMS", "Remittance Requested", "Invoice Resent"]:
        new_status = "In Follow Up"

    if outcome == "Awaiting Response":
        new_status = "Waiting For Response"

    if outcome == "Escalated" or activity_type == "Escalation":
        new_status = "Escalated"
        case.escalated_on = now_datetime()

    if outcome == "Resolved" or activity_type == "Resolved":
        new_status = "Resolved"
        case.resolved_on = now_datetime()

    if outcome == "Closed":
        new_status = "Closed"
        case.resolved_on = now_datetime()

    case.status = new_status
    case.last_follow_up_on = activity.activity_datetime
    case.next_follow_up_date = next_follow_up_date
    case.last_activity_note = activity_note
    case.save(ignore_permissions=True)

    propagate_case_status(case)

    if commit:
        frappe.db.commit()

    return {
        "recovery_case": recovery_case,
        "activity": activity.name,
        "case_status": case.status,
        "next_follow_up_date": case.next_follow_up_date,
    }


@frappe.whitelist()
def add_recovery_activity(
    recovery_case,
    activity_type="Note",
    outcome=None,
    activity_note=None,
    next_follow_up_date=None,
    attachment=None,
    commit=True,
):
    assert_action("add_recovery_activity")

    return log_recovery_activity(
        recovery_case=recovery_case,
        activity_type=activity_type,
        outcome=outcome,
        activity_note=activity_note,
        next_follow_up_date=next_follow_up_date,
        attachment=attachment,
        commit=commit,
    )


@frappe.whitelist()
def escalate_recovery_case(recovery_case, reason=None, next_follow_up_date=None):
    assert_action("escalate_recovery_case")

    note = reason or "Recovery case escalated for management review."

    return add_recovery_activity(
        recovery_case=recovery_case,
        activity_type="Escalation",
        outcome="Escalated",
        activity_note=note,
        next_follow_up_date=next_follow_up_date or add_days(nowdate(), 2),
    )


@frappe.whitelist()
def resolve_recovery_case(recovery_case, recovered_amount=0, resolution_note=None):
    """
    Resolve a recovery case after payment/recovery has been completed.
    """

    assert_action("resolve_recovery_case")

    if not frappe.db.exists("NDIS Recovery Case", recovery_case):
        frappe.throw(_("Recovery Case not found: {0}").format(recovery_case))

    case = frappe.get_doc("NDIS Recovery Case", recovery_case)

    case.status = "Resolved"
    case.recovered_amount = flt(recovered_amount)
    case.resolved_on = now_datetime()
    case.resolution_note = resolution_note or "Recovery case resolved."
    case.outstanding_amount = max(flt(case.outstanding_amount) - flt(recovered_amount), 0)
    case.save(ignore_permissions=True)

    log_recovery_activity(
        recovery_case=case.name,
        activity_type="Resolved",
        outcome="Resolved",
        activity_note=case.resolution_note,
        next_follow_up_date=None,
        commit=False,
    )

    propagate_case_status(frappe.get_doc("NDIS Recovery Case", case.name))

    frappe.db.commit()

    return {
        "recovery_case": case.name,
        "status": "Resolved",
        "recovered_amount": flt(recovered_amount),
        "remaining_outstanding_amount": flt(
            frappe.db.get_value("NDIS Recovery Case", case.name, "outstanding_amount")
        ),
    }


@frappe.whitelist()
def write_off_recovery_case(recovery_case, written_off_amount=None, resolution_note=None):
    """
    Control-level write-off marking only.
    This does not create Journal Entry or GL movement.
    Accounting write-off must still be done through standard ERPNext accounting controls.
    """

    assert_action("write_off_recovery_case")

    if not frappe.db.exists("NDIS Recovery Case", recovery_case):
        frappe.throw(_("Recovery Case not found: {0}").format(recovery_case))

    case = frappe.get_doc("NDIS Recovery Case", recovery_case)

    amount = flt(written_off_amount) if written_off_amount is not None else flt(case.outstanding_amount)

    case.status = "Written Off"
    case.written_off_amount = amount
    case.resolved_on = now_datetime()
    case.resolution_note = resolution_note or "Marked for write-off control review."
    case.save(ignore_permissions=True)

    log_recovery_activity(
        recovery_case=case.name,
        activity_type="Write Off Approved",
        outcome="Write Off Approved",
        activity_note=case.resolution_note,
        next_follow_up_date=None,
        commit=False,
    )

    propagate_case_status(frappe.get_doc("NDIS Recovery Case", case.name))

    frappe.db.commit()

    return {
        "recovery_case": case.name,
        "status": "Written Off",
        "written_off_amount": amount,
        "note": "Control status updated only. Complete accounting write-off through ERPNext if approved.",
    }


@frappe.whitelist()
def close_recovery_case(recovery_case, resolution_note=None):
    assert_action("close_recovery_case")

    if not frappe.db.exists("NDIS Recovery Case", recovery_case):
        frappe.throw(_("Recovery Case not found: {0}").format(recovery_case))

    case = frappe.get_doc("NDIS Recovery Case", recovery_case)

    case.status = "Closed"
    case.resolved_on = now_datetime()
    case.resolution_note = resolution_note or "Recovery case closed."
    case.save(ignore_permissions=True)

    log_recovery_activity(
        recovery_case=case.name,
        activity_type="Note",
        outcome="Closed",
        activity_note=case.resolution_note,
        next_follow_up_date=None,
        commit=False,
    )

    propagate_case_status(frappe.get_doc("NDIS Recovery Case", case.name))

    frappe.db.commit()

    return {
        "recovery_case": case.name,
        "status": "Closed",
    }


def propagate_case_status(case):
    recovery_status = map_case_status_to_recovery_status(case.status)

    if case.funding_leakage:
        leakage_status = "Open"

        if case.status == "Resolved":
            leakage_status = "Resolved"
        elif case.status == "Written Off":
            leakage_status = "Written Off"
        elif case.status == "Closed":
            leakage_status = "Closed"
        elif case.status in ["In Follow Up", "Waiting For Response", "Escalated"]:
            leakage_status = "In Review"

        safe_db_set("NDIS Funding Leakage Register", case.funding_leakage, "status", leakage_status)
        safe_db_set(
            "NDIS Funding Leakage Register",
            case.funding_leakage,
            "recovery_status",
            recovery_status,
        )
        safe_db_set(
            "NDIS Funding Leakage Register",
            case.funding_leakage,
            "follow_up_due_date",
            case.next_follow_up_date,
        )
        safe_db_set("NDIS Funding Leakage Register", case.funding_leakage, "assigned_to", case.assigned_to)

    if case.claim_line:
        safe_db_set("NDIS Claim Line", case.claim_line, "recovery_status", recovery_status)
        safe_db_set("NDIS Claim Line", case.claim_line, "follow_up_due_date", case.next_follow_up_date)

    if case.sales_invoice:
        refresh_invoice_recovery_status(case.sales_invoice)


def map_case_status_to_recovery_status(case_status):
    mapping = {
        "Open": "Open",
        "In Follow Up": "In Follow Up",
        "Waiting For Response": "In Follow Up",
        "Escalated": "Escalated",
        "Resolved": "Resolved",
        "Written Off": "Written Off",
        "Closed": "Resolved",
    }

    return mapping.get(case_status, "Open")


@frappe.whitelist()
def refresh_invoice_recovery_status(sales_invoice):
    if not frappe.db.exists("Sales Invoice", sales_invoice):
        frappe.throw(_("Sales Invoice not found: {0}").format(sales_invoice))

    cases = frappe.get_all(
        "NDIS Recovery Case",
        filters={"sales_invoice": sales_invoice},
        fields=["name", "status", "last_follow_up_on", "next_follow_up_date"],
        order_by="modified desc",
    )

    case_count = len(cases)
    last_case = cases[0].name if cases else None

    statuses = {case.status for case in cases}

    if not cases:
        recovery_status = "Not Due"
    elif "Escalated" in statuses:
        recovery_status = "Escalated"
    elif statuses.intersection({"Open", "In Follow Up", "Waiting For Response"}):
        recovery_status = "In Follow Up"
    elif "Written Off" in statuses:
        recovery_status = "Do Not Recover"
    elif statuses.issubset({"Resolved", "Closed"}):
        recovery_status = "Resolved"
    else:
        recovery_status = "Follow Up Required"

    last_follow_up = None
    next_follow_up = None

    for case in cases:
        if case.last_follow_up_on and not last_follow_up:
            last_follow_up = case.last_follow_up_on
        if case.next_follow_up_date and not next_follow_up:
            next_follow_up = case.next_follow_up_date

    updates = {
        "custom_ndis_recovery_status": recovery_status,
        "custom_ndis_recovery_case_count": case_count,
        "custom_ndis_last_recovery_case": last_case,
        "custom_ndis_last_follow_up_on": last_follow_up,
        "custom_ndis_next_follow_up_date": next_follow_up,
    }

    for fieldname, value in updates.items():
        safe_db_set("Sales Invoice", sales_invoice, fieldname, value)

    return {
        "sales_invoice": sales_invoice,
        "recovery_status": recovery_status,
        "case_count": case_count,
        "last_recovery_case": last_case,
        "last_follow_up_on": last_follow_up,
        "next_follow_up_date": next_follow_up,
    }


@frappe.whitelist()
def quick_recovery_summary(limit=20):
    cases = frappe.get_all(
        "NDIS Recovery Case",
        fields=[
            "name",
            "case_id",
            "case_type",
            "status",
            "priority",
            "assigned_to",
            "participant",
            "funding_source",
            "sales_invoice",
            "claim_line",
            "expected_amount",
            "paid_amount",
            "outstanding_amount",
            "recovered_amount",
            "next_follow_up_date",
        ],
        order_by="modified desc",
        limit=int(limit or 20),
    )

    activities = frappe.get_all(
        "NDIS Recovery Activity",
        fields=[
            "name",
            "recovery_case",
            "activity_datetime",
            "activity_type",
            "performed_by",
            "outcome",
            "next_follow_up_date",
            "activity_note",
        ],
        order_by="modified desc",
        limit=int(limit or 20),
    )

    return {
        "cases": cases,
        "activities": activities,
    }


@frappe.whitelist()
def quick_overdue_recovery_cases(limit=20):
    return frappe.get_all(
        "NDIS Recovery Case",
        filters={
            "status": ["in", OPEN_CASE_STATUSES],
            "next_follow_up_date": ["<=", nowdate()],
        },
        fields=[
            "name",
            "case_id",
            "case_type",
            "status",
            "priority",
            "assigned_to",
            "participant",
            "sales_invoice",
            "outstanding_amount",
            "next_follow_up_date",
        ],
        order_by="next_follow_up_date asc",
        limit=int(limit or 20),
    )
