import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


PREVIEW_ONLY_CONFIRMATION = "PREVIEW_ONLY_NO_ACCOUNTING_POSTING"


def currency():
    return frappe.defaults.get_global_default("currency") or "AUD"


def make_preview_id(event_type="Preview"):
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    safe_event = frappe.scrub(event_type or "Preview").replace("_", "-").upper()
    return f"NDIS-ACC-PREVIEW-{safe_event}-{timestamp}-{frappe.generate_hash(length=5).upper()}"


def get_policy(policy=None, event_type=None, source_doctype=None):
    if policy:
        if not frappe.db.exists("NDIS Accounting Posting Policy", policy):
            frappe.throw(_("Accounting Posting Policy not found: {0}").format(policy))
        return frappe.get_doc("NDIS Accounting Posting Policy", policy)

    filters = {"active": 1, "policy_status": "Active"}
    if event_type:
        filters["event_type"] = event_type
    if source_doctype:
        filters["source_doctype"] = source_doctype

    rows = frappe.get_all("NDIS Accounting Posting Policy", filters=filters, fields=["name"], order_by="modified desc", limit=1)
    if not rows:
        frappe.throw(_("No active NDIS Accounting Posting Policy found for event_type={0}, source_doctype={1}").format(event_type or "", source_doctype or ""))
    return frappe.get_doc("NDIS Accounting Posting Policy", rows[0].name)


def get_latest_allowed_readiness_check():
    rows = frappe.get_all(
        "NDIS Finance Production Readiness Check",
        filters={"status": ["in", ["Passed", "Needs Review"]], "production_ready_allowed": 1},
        fields=["name"],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0].name if rows else None


def get_latest_signed_governance_pack():
    rows = frappe.get_all(
        "NDIS Executive Governance Pack",
        filters={"status": "Signed Off", "management_sign_off": 1},
        fields=["name"],
        order_by="pack_date desc, creation desc",
        limit=1,
    )
    return rows[0].name if rows else None


def get_source_doc(source_doctype, source_name):
    if not frappe.db.exists("DocType", source_doctype):
        frappe.throw(_("Source DocType does not exist: {0}").format(source_doctype))
    if not frappe.db.exists(source_doctype, source_name):
        frappe.throw(_("{0} not found: {1}").format(source_doctype, source_name))
    return frappe.get_doc(source_doctype, source_name)


def first_existing_value(doc, fieldnames, default=None):
    for fieldname in fieldnames:
        if doc.meta.has_field(fieldname):
            value = doc.get(fieldname)
            if value not in [None, ""]:
                return value
    return default


def derive_source_amount(doc):
    for fieldname in [
        "total_amount",
        "total_claim_amount",
        "claim_amount",
        "total_received_amount",
        "received_amount",
        "allocated_amount",
        "total_import_cost_amount",
        "total_cost_amount",
        "outstanding_amount",
        "recovered_amount",
        "written_off_amount",
        "shortfall_amount",
        "estimated_margin",
        "paid_revenue",
    ]:
        if doc.meta.has_field(fieldname):
            value = flt(doc.get(fieldname))
            if value:
                return abs(value)
    return 0


def derive_source_status(doc):
    for fieldname in ["status", "workflow_state", "claim_status", "docstatus"]:
        if doc.meta.has_field(fieldname):
            value = doc.get(fieldname)
            if value not in [None, ""]:
                return str(value)
    return ""


def derive_company(doc, policy_doc=None):
    return first_existing_value(doc, ["company"]) or (policy_doc.company if policy_doc else None) or frappe.defaults.get_user_default("Company")


def derive_source_summary(doc, amount):
    parts = []
    status = derive_source_status(doc)
    if status:
        parts.append(f"Status: {status}")
    for fieldname in ["period_start", "period_end", "from_date", "to_date", "snapshot_date", "pack_date"]:
        if doc.meta.has_field(fieldname):
            value = doc.get(fieldname)
            if value:
                parts.append(f"{fieldname}: {value}")
    parts.append(f"Preview amount: {flt(amount):.2f}")
    return "; ".join(parts)


def validate_readiness(policy_doc, readiness_check=None):
    if not int(policy_doc.requires_readiness_check or 0):
        return None, 1, []

    readiness_check = readiness_check or get_latest_allowed_readiness_check()
    validation = []
    if not readiness_check:
        validation.append({"status": "Blocker", "label": "Missing production readiness check", "detail": "Policy requires an allowed Production Readiness Check but none was supplied/found."})
        return None, 0, validation

    allowed = frappe.db.get_value("NDIS Finance Production Readiness Check", readiness_check, "production_ready_allowed")
    status = frappe.db.get_value("NDIS Finance Production Readiness Check", readiness_check, "status")
    if not int(allowed or 0):
        validation.append({"status": "Blocker", "label": "Production readiness not allowed", "detail": f"Readiness check {readiness_check} exists but production_ready_allowed is not enabled."})
    if status == "Cancelled":
        validation.append({"status": "Blocker", "label": "Readiness check cancelled", "detail": f"Readiness check {readiness_check} is cancelled."})
    return readiness_check, int(allowed or 0), validation


def validate_governance(policy_doc, governance_pack=None):
    if not int(policy_doc.requires_governance_pack_signoff or 0):
        return None, 1, []

    governance_pack = governance_pack or get_latest_signed_governance_pack()
    validation = []
    if not governance_pack:
        validation.append({"status": "Blocker", "label": "Missing signed governance pack", "detail": "Policy requires signed governance pack but none was supplied/found."})
        return None, 0, validation

    signed = frappe.db.get_value("NDIS Executive Governance Pack", governance_pack, "management_sign_off")
    status = frappe.db.get_value("NDIS Executive Governance Pack", governance_pack, "status")
    if not int(signed or 0) or status != "Signed Off":
        validation.append({"status": "Blocker", "label": "Governance pack not signed off", "detail": f"Governance pack {governance_pack} is not signed off."})
    return governance_pack, int(signed or 0), validation


def validate_policy_safety(policy_doc):
    validation = []
    if policy_doc.posting_mode == "Disabled":
        validation.append({"status": "Blocker", "label": "Policy disabled", "detail": "This accounting posting policy is disabled."})
    if policy_doc.posting_mode == "Future Controlled Posting":
        validation.append({"status": "Warning", "label": "Future controlled posting policy", "detail": "Policy is marked as Future Controlled Posting, but Phase 2B remains preview-only."})
    if int(policy_doc.allow_gl_entry or 0):
        validation.append({"status": "Blocker", "label": "Direct GL Entry creation is not allowed", "detail": "Policy allows GL Entry creation. Phase 2B blocks this."})

    risky_allowed = []
    if int(policy_doc.allow_sales_invoice or 0):
        risky_allowed.append("Sales Invoice")
    if int(policy_doc.allow_payment_entry or 0):
        risky_allowed.append("Payment Entry")
    if int(policy_doc.allow_journal_entry or 0):
        risky_allowed.append("Journal Entry")
    if risky_allowed:
        validation.append({"status": "Warning", "label": "Future posting flag enabled", "detail": "Policy has future posting flag(s) enabled: " + ", ".join(risky_allowed) + ". Phase 2B still creates preview only."})
    return validation


def build_preview_lines(policy_doc, source_doc, amount):
    target = policy_doc.target_entry_type or "None"
    if policy_doc.posting_mode == "Management Only" or target == "None":
        return [
            {
                "status": "Preview",
                "line_label": "Management-only control line",
                "line_type": "Information",
                "target_entry_type": target,
                "amount": amount,
                "reference_doctype": source_doc.doctype,
                "reference_name": source_doc.name,
                "note": "Policy is management-only. No accounting entry should be created.",
            }
        ]

    lines = []
    if not policy_doc.default_debit_account:
        lines.append({"status": "Warning", "line_label": "Missing debit account", "line_type": "Control", "target_entry_type": target, "amount": 0, "reference_doctype": source_doc.doctype, "reference_name": source_doc.name, "note": "Debit account is not mapped. Future posting must not proceed without explicit account mapping."})
    if not policy_doc.default_credit_account:
        lines.append({"status": "Warning", "line_label": "Missing credit account", "line_type": "Control", "target_entry_type": target, "amount": 0, "reference_doctype": source_doc.doctype, "reference_name": source_doc.name, "note": "Credit account is not mapped. Future posting must not proceed without explicit account mapping."})
    lines.extend(
        [
            {"status": "Preview", "line_label": "Preview Debit", "line_type": "Debit", "target_entry_type": target, "account": policy_doc.default_debit_account, "cost_center": policy_doc.default_cost_center, "amount": amount, "reference_doctype": source_doc.doctype, "reference_name": source_doc.name, "note": "Preview-only debit line. No accounting document created."},
            {"status": "Preview", "line_label": "Preview Credit", "line_type": "Credit", "target_entry_type": target, "account": policy_doc.default_credit_account, "cost_center": policy_doc.default_cost_center, "amount": amount, "reference_doctype": source_doc.doctype, "reference_name": source_doc.name, "note": "Preview-only credit line. No accounting document created."},
        ]
    )
    return lines


def summarise_validation(validation_items):
    blocker_count = len([row for row in validation_items if row["status"] == "Blocker"])
    warning_count = len([row for row in validation_items if row["status"] == "Warning"])
    if blocker_count:
        return "Blocked", "Blocked", blocker_count, warning_count
    if warning_count:
        return "Previewed", "Warning", blocker_count, warning_count
    return "Previewed", "Pass", blocker_count, warning_count


@frappe.whitelist()
def create_accounting_posting_preview(source_doctype, source_name, policy=None, event_type=None, readiness_check=None, governance_pack=None, dry_run=0, notes=None):
    assert_action("create_accounting_posting_preview")

    policy_doc = get_policy(policy=policy, event_type=event_type, source_doctype=source_doctype)
    source_doc = get_source_doc(source_doctype, source_name)
    if policy_doc.source_doctype != source_doctype:
        frappe.throw(_("Policy source DocType {0} does not match requested source DocType {1}.").format(policy_doc.source_doctype, source_doctype))

    amount = derive_source_amount(source_doc)
    validation_items = []
    validation_items.extend(validate_policy_safety(policy_doc))
    readiness_check, readiness_allowed, readiness_validation = validate_readiness(policy_doc, readiness_check)
    validation_items.extend(readiness_validation)
    governance_pack, governance_signed_off, governance_validation = validate_governance(policy_doc, governance_pack)
    validation_items.extend(governance_validation)
    if amount <= 0:
        validation_items.append({"status": "Warning", "label": "Zero preview amount", "detail": "Source amount could not be determined or is zero. This may be valid for governance/control records."})

    lines = build_preview_lines(policy_doc, source_doc, amount)
    for line in lines:
        if line.get("status") in ["Warning", "Blocker"]:
            validation_items.append({"status": line.get("status"), "label": line.get("line_label"), "detail": line.get("note")})

    status, validation_status, blocker_count, warning_count = summarise_validation(validation_items)
    source_status = derive_source_status(source_doc)
    source_summary = derive_source_summary(source_doc, amount)

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "policy": policy_doc.name,
        "policy_id": policy_doc.policy_id,
        "event_type": policy_doc.event_type,
        "source_doctype": source_doctype,
        "source_name": source_name,
        "source_status": source_status,
        "source_summary": source_summary,
        "readiness_check": readiness_check,
        "readiness_allowed": readiness_allowed,
        "governance_pack": governance_pack,
        "governance_signed_off": governance_signed_off,
        "target_entry_type": policy_doc.target_entry_type,
        "posting_mode": policy_doc.posting_mode,
        "preview_total_amount": amount,
        "status": status,
        "validation_status": validation_status,
        "blocker_count": blocker_count,
        "warning_count": warning_count,
        "validation_items": validation_items,
        "preview_lines": lines,
        "note": "Preview only. No Payment Entry, Journal Entry, GL Entry, Sales Invoice, Purchase Invoice, payroll posting, STP, ABA, email, or payment movement created.",
    }
    if int(dry_run or 0):
        return result

    doc = frappe.new_doc("NDIS Accounting Posting Preview")
    doc.preview_id = make_preview_id(policy_doc.event_type)
    doc.status = status
    doc.validation_status = validation_status
    doc.event_type = policy_doc.event_type
    doc.policy = policy_doc.name
    doc.source_doctype = source_doctype
    doc.source_name = source_name
    doc.source_status = source_status
    doc.source_summary = source_summary
    doc.readiness_check = readiness_check
    doc.readiness_allowed = int(readiness_allowed or 0)
    doc.governance_pack = governance_pack
    doc.governance_signed_off = int(governance_signed_off or 0)
    doc.cfo_approval_required = int(policy_doc.requires_cfo_approval or 0)
    doc.target_entry_type = policy_doc.target_entry_type
    doc.posting_mode = policy_doc.posting_mode
    doc.company = derive_company(source_doc, policy_doc)
    doc.posting_date = today()
    doc.currency = currency()
    doc.preview_total_amount = amount
    doc.line_count = len(lines)
    doc.blocker_count = blocker_count
    doc.warning_count = warning_count
    doc.preview_only_confirmation = PREVIEW_ONLY_CONFIRMATION
    doc.created_on = now_datetime()
    doc.created_by_user = frappe.session.user
    doc.validation_log = frappe.as_json(validation_items, indent=2)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    for idx, line in enumerate(lines, start=1):
        row = frappe.new_doc("NDIS Accounting Posting Preview Line")
        row.posting_preview = doc.name
        row.status = line.get("status") or "Preview"
        row.line_no = idx
        row.line_label = line.get("line_label")
        row.line_type = line.get("line_type")
        row.target_entry_type = line.get("target_entry_type")
        row.account = line.get("account")
        row.cost_center = line.get("cost_center")
        row.party_type = line.get("party_type")
        row.party = line.get("party")
        row.amount = flt(line.get("amount"))
        row.reference_doctype = line.get("reference_doctype")
        row.reference_name = line.get("reference_name")
        row.note = line.get("note")
        row.insert(ignore_permissions=True)

    refresh_policy_preview_count(policy_doc.name, doc.name)
    frappe.db.commit()

    result["created"] = True
    result["posting_preview"] = doc.name
    result["preview_id"] = doc.preview_id
    return result


@frappe.whitelist()
def refresh_policy_preview_count(policy, latest_preview=None):
    if not frappe.db.exists("NDIS Accounting Posting Policy", policy):
        frappe.throw(_("Accounting Posting Policy not found: {0}").format(policy))
    count = frappe.db.count("NDIS Accounting Posting Preview", {"policy": policy, "status": ["!=", "Cancelled"]})
    values = {"preview_count": count, "last_preview_on": now_datetime()}
    if latest_preview:
        values["last_preview"] = latest_preview
    frappe.db.set_value("NDIS Accounting Posting Policy", policy, values, update_modified=False)
    return {"policy": policy, "preview_count": count, "last_preview": latest_preview}


@frappe.whitelist()
def cancel_accounting_posting_preview(posting_preview, reason=None):
    assert_action("cancel_accounting_posting_preview")
    if not frappe.db.exists("NDIS Accounting Posting Preview", posting_preview):
        frappe.throw(_("Accounting Posting Preview not found: {0}").format(posting_preview))
    policy = frappe.db.get_value("NDIS Accounting Posting Preview", posting_preview, "policy")
    frappe.db.set_value(
        "NDIS Accounting Posting Preview",
        posting_preview,
        {"status": "Cancelled", "cancelled_on": now_datetime(), "cancelled_by": frappe.session.user, "validation_log": reason or "Posting preview cancelled."},
        update_modified=False,
    )
    frappe.db.sql("UPDATE `tabNDIS Accounting Posting Preview Line` SET status = 'Cancelled' WHERE posting_preview = %(posting_preview)s", {"posting_preview": posting_preview})
    if policy:
        refresh_policy_preview_count(policy)
    frappe.db.commit()
    return {"posting_preview": posting_preview, "status": "Cancelled", "note": "Posting preview cancelled only. No accounting, payroll, STP, ABA, email, or payment movement was changed."}


@frappe.whitelist()
def quick_accounting_policy_summary(limit=20):
    policies = frappe.get_all(
        "NDIS Accounting Posting Policy",
        fields=[
            "name",
            "policy_id",
            "policy_name",
            "policy_status",
            "active",
            "event_type",
            "source_doctype",
            "target_entry_type",
            "posting_mode",
            "requires_readiness_check",
            "requires_governance_pack_signoff",
            "requires_cfo_approval",
            "allow_sales_invoice",
            "allow_payment_entry",
            "allow_journal_entry",
            "allow_gl_entry",
            "preview_count",
            "last_preview_on",
        ],
        order_by="event_type asc, policy_name asc",
        limit=int(limit or 20),
    )
    previews = frappe.get_all(
        "NDIS Accounting Posting Preview",
        fields=["name", "preview_id", "status", "validation_status", "event_type", "policy", "source_doctype", "source_name", "target_entry_type", "posting_mode", "preview_total_amount", "blocker_count", "warning_count", "created_on"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "policies": policies,
        "previews": previews,
        "preview_only_confirmation": PREVIEW_ONLY_CONFIRMATION,
        "note": "Accounting policy summary only. No Payment Entry, Journal Entry, GL Entry, Sales Invoice, Purchase Invoice, payroll posting, STP, ABA, email, or payment movement created.",
    }


def execute_policy_register_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    for fieldname in ["policy_status", "event_type", "source_doctype", "posting_mode"]:
        if filters.get(fieldname):
            conditions.append(f"p.{fieldname} = %({fieldname})s")
            params[fieldname] = filters.get(fieldname)

    columns = [
        {"fieldname": "policy", "label": _("Policy"), "fieldtype": "Link", "options": "NDIS Accounting Posting Policy", "width": 220},
        {"fieldname": "policy_id", "label": _("Policy ID"), "fieldtype": "Data", "width": 280},
        {"fieldname": "policy_name", "label": _("Policy Name"), "fieldtype": "Data", "width": 300},
        {"fieldname": "policy_status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "event_type", "label": _("Event Type"), "fieldtype": "Data", "width": 170},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 210},
        {"fieldname": "target_entry_type", "label": _("Target Entry"), "fieldtype": "Data", "width": 140},
        {"fieldname": "posting_mode", "label": _("Posting Mode"), "fieldtype": "Data", "width": 170},
        {"fieldname": "requires_readiness_check", "label": _("Readiness"), "fieldtype": "Check", "width": 90},
        {"fieldname": "requires_governance_pack_signoff", "label": _("Governance"), "fieldtype": "Check", "width": 100},
        {"fieldname": "requires_cfo_approval", "label": _("CFO"), "fieldtype": "Check", "width": 70},
        {"fieldname": "allow_sales_invoice", "label": _("SI"), "fieldtype": "Check", "width": 60},
        {"fieldname": "allow_payment_entry", "label": _("PE"), "fieldtype": "Check", "width": 60},
        {"fieldname": "allow_journal_entry", "label": _("JE"), "fieldtype": "Check", "width": 60},
        {"fieldname": "allow_gl_entry", "label": _("GL"), "fieldtype": "Check", "width": 60},
        {"fieldname": "preview_count", "label": _("Previews"), "fieldtype": "Int", "width": 90},
        {"fieldname": "description", "label": _("Description"), "fieldtype": "Small Text", "width": 380},
    ]
    data = frappe.db.sql(
        f"""
        SELECT p.name AS policy, p.policy_id, p.policy_name, p.policy_status, p.event_type,
               p.source_doctype, p.target_entry_type, p.posting_mode, p.requires_readiness_check,
               p.requires_governance_pack_signoff, p.requires_cfo_approval, p.allow_sales_invoice,
               p.allow_payment_entry, p.allow_journal_entry, p.allow_gl_entry, p.preview_count,
               p.description
        FROM `tabNDIS Accounting Posting Policy` p
        {build_where(conditions)}
        ORDER BY p.event_type ASC, p.policy_name ASC
        """,
        params,
        as_dict=True,
    )
    chart_map = {}
    for row in data:
        chart_map[row.posting_mode or "Unknown"] = chart_map.get(row.posting_mode or "Unknown", 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Policies", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Policies"), "datatype": "Int"},
        {"value": len([row for row in data if row.posting_mode == "Management Only"]), "indicator": "Green", "label": _("Management Only"), "datatype": "Int"},
        {"value": len([row for row in data if row.posting_mode == "Preview Only"]), "indicator": "Orange", "label": _("Preview Only"), "datatype": "Int"},
        {"value": len([row for row in data if row.allow_gl_entry]), "indicator": "Red", "label": _("GL Allowed Flags"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_posting_preview_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    for fieldname in ["status", "validation_status", "event_type", "policy", "source_doctype"]:
        if filters.get(fieldname):
            conditions.append(f"p.{fieldname} = %({fieldname})s")
            params[fieldname] = filters.get(fieldname)
    if filters.get("from_date"):
        conditions.append("DATE(p.created_on) >= %(from_date)s")
        params["from_date"] = filters.get("from_date")
    if filters.get("to_date"):
        conditions.append("DATE(p.created_on) <= %(to_date)s")
        params["to_date"] = filters.get("to_date")
    params["currency"] = currency()

    columns = [
        {"fieldname": "posting_preview", "label": _("Posting Preview"), "fieldtype": "Link", "options": "NDIS Accounting Posting Preview", "width": 220},
        {"fieldname": "preview_id", "label": _("Preview ID"), "fieldtype": "Data", "width": 300},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "validation_status", "label": _("Validation"), "fieldtype": "Data", "width": 110},
        {"fieldname": "event_type", "label": _("Event Type"), "fieldtype": "Data", "width": 160},
        {"fieldname": "policy", "label": _("Policy"), "fieldtype": "Link", "options": "NDIS Accounting Posting Policy", "width": 220},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 190},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Data", "width": 220},
        {"fieldname": "target_entry_type", "label": _("Target Entry"), "fieldtype": "Data", "width": 130},
        {"fieldname": "posting_mode", "label": _("Posting Mode"), "fieldtype": "Data", "width": 160},
        {"fieldname": "preview_total_amount", "label": _("Preview Amount"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "line_count", "label": _("Lines"), "fieldtype": "Int", "width": 80},
        {"fieldname": "blocker_count", "label": _("Blockers"), "fieldtype": "Int", "width": 90},
        {"fieldname": "warning_count", "label": _("Warnings"), "fieldtype": "Int", "width": 90},
        {"fieldname": "readiness_allowed", "label": _("Readiness"), "fieldtype": "Check", "width": 90},
        {"fieldname": "governance_signed_off", "label": _("Governance"), "fieldtype": "Check", "width": 100},
        {"fieldname": "created_on", "label": _("Created On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT p.name AS posting_preview, p.preview_id, p.status, p.validation_status, p.event_type,
               p.policy, p.source_doctype, p.source_name, p.target_entry_type, p.posting_mode,
               p.preview_total_amount, p.line_count, p.blocker_count, p.warning_count,
               p.readiness_allowed, p.governance_signed_off, p.created_on, %(currency)s AS currency
        FROM `tabNDIS Accounting Posting Preview` p
        {build_where(conditions)}
        ORDER BY p.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.preview_id for row in data[:20]],
            "datasets": [
                {"name": "Preview Amount", "values": [flt(row.preview_total_amount) for row in data[:20]]},
                {"name": "Warnings", "values": [int(row.warning_count or 0) for row in data[:20]]},
                {"name": "Blockers", "values": [int(row.blocker_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Previews"), "datatype": "Int"},
        {"value": sum(flt(row.preview_total_amount) for row in data), "indicator": "Blue", "label": _("Preview Amount"), "datatype": "Currency", "currency": currency()},
        {"value": len([row for row in data if row.validation_status == "Blocked"]), "indicator": "Red", "label": _("Blocked"), "datatype": "Int"},
        {"value": len([row for row in data if row.validation_status == "Warning"]), "indicator": "Orange", "label": _("Warnings"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
