import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


GATE_DOCTYPE = "NDIS Real Remittance PE Design Gate"
ITEM_DOCTYPE = "NDIS Real Remittance PE Design Gate Item"
DESIGN_ACK = "I_CONFIRM_PHASE6A_REAL_REMITTANCE_PE_DESIGN_ONLY_NO_POSTING"

DEFAULT_COMPANY = "CONNECTUS HOME CARE PTY LTD"
DEFAULT_BANK_ACCOUNT = "11510 - Every Day Bank Account - CHCPL"
DEFAULT_RECEIVABLE_ACCOUNT = "12010 - Trade Debtors - CHCPL"


def make_gate_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-REAL-REMITTANCE-PE-DESIGN-{timestamp}-{frappe.generate_hash(length=5).upper()}"


def currency():
    return frappe.defaults.get_global_default("currency") or "AUD"


def safe_json(value):
    try:
        return json.dumps(value, indent=2, default=str)
    except Exception:
        return str(value)


def count_dt(doctype, filters=None):
    if not frappe.db.exists("DocType", doctype):
        return 0
    return frappe.db.count(doctype, filters or {})


def add_item(items, status, severity, category, check_key, check_label, detail, recommendation=None, source_doctype=None, source_name=None):
    items.append(
        {
            "status": status,
            "severity": severity,
            "category": category,
            "check_key": check_key,
            "check_label": check_label,
            "detail": detail,
            "recommendation": recommendation,
            "source_doctype": source_doctype,
            "source_name": source_name,
        }
    )


def config_state():
    return {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def guardrails():
    return {
        "payment_entry_count": count_dt("Payment Entry"),
        "payment_entry_gl_count": count_dt("GL Entry", {"voucher_type": "Payment Entry"}),
        "gl_entry_count_today": count_dt("GL Entry", {"creation": [">=", today()]}),
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
        "sales_invoice_count_today": count_dt("Sales Invoice", {"creation": [">=", today()]}),
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
        "live_enabled_policy_count": count_dt("NDIS PE Production Posting Policy", {"production_posting_enabled": 1}),
    }


def latest_phase5k_freeze():
    rows = frappe.get_all(
        "NDIS PE Live Smoke Completion Freeze",
        filters={
            "status": "Frozen",
            "completion_freeze_allowed": 1,
            "ready_for_next_phase": 1,
            "payment_entry_gl_net": 0,
            "sales_invoice_gl_net": 0,
            "submitted_phase5i_pe_count": 0,
            "active_phase5h_source_invoice_count": 0,
            "live_enabled_policy_count": 0,
        },
        fields=["name", "completion_freeze_id", "phase5j_rollback_run", "phase5i_run"],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def evaluate_config(items):
    config = config_state()
    if config["production_mode"]:
        add_item(items, "Blocker", "Critical", "Site Config", "production_mode", "Production mode", "Production mode is enabled.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "production_mode", "Production mode", "Production mode remains disabled.")

    if config["live_pe_enabled"]:
        add_item(items, "Blocker", "Critical", "Site Config", "live_pe_enabled", "Live PE posting config", "Live Payment Entry posting config is enabled.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "live_pe_enabled", "Live PE posting config", "Live Payment Entry posting remains disabled.")

    if config["sandbox_enabled"]:
        add_item(items, "Pass", "Low", "Site Config", "sandbox_enabled", "Sandbox config", "Sandbox config remains enabled.")
    else:
        add_item(items, "Warning", "Medium", "Site Config", "sandbox_enabled", "Sandbox config", "Sandbox config is not enabled.")
    return config


def evaluate_phase5k(items):
    freeze = latest_phase5k_freeze()
    if freeze:
        add_item(
            items,
            "Pass",
            "Low",
            "Prior Evidence",
            "phase5k_freeze",
            "Phase 5K completion freeze",
            f"Valid Phase 5K freeze found: {freeze.completion_freeze_id}.",
            None,
            "NDIS PE Live Smoke Completion Freeze",
            freeze.name,
        )
    else:
        add_item(
            items,
            "Blocker",
            "Critical",
            "Prior Evidence",
            "phase5k_freeze",
            "Phase 5K completion freeze",
            "No valid frozen Phase 5K completion evidence found.",
            "Complete Phase 5K before Phase 6A.",
        )
    return freeze


def evaluate_accounts(items, company, bank_account, receivable_account):
    if not frappe.db.exists("Company", company):
        add_item(items, "Blocker", "Critical", "Account Scope", "company", "Company", f"Company not found: {company}.")
    else:
        add_item(items, "Pass", "Low", "Account Scope", "company", "Company", f"Company verified: {company}.", None, "Company", company)

    bank_ok = validate_account(items, bank_account, company, "Bank account", "bank_account")
    receivable_ok = validate_account(items, receivable_account, company, "Receivable account", "receivable_account", require_receivable=True)
    return bank_ok and receivable_ok


def validate_account(items, account, company, label, key, require_receivable=False):
    if not account or not frappe.db.exists("Account", account):
        add_item(items, "Blocker", "Critical", "Account Scope", key, label, f"{label} not found: {account}.")
        return False

    doc = frappe.get_doc("Account", account)
    if doc.company != company:
        add_item(items, "Blocker", "Critical", "Account Scope", key, label, f"{label} belongs to {doc.company}, expected {company}.")
        return False
    if int(doc.is_group or 0):
        add_item(items, "Blocker", "Critical", "Account Scope", key, label, f"{label} is a group account.")
        return False
    if int(doc.disabled or 0):
        add_item(items, "Blocker", "Critical", "Account Scope", key, label, f"{label} is disabled.")
        return False
    if require_receivable and doc.account_type and doc.account_type != "Receivable":
        add_item(items, "Blocker", "Critical", "Account Scope", key, label, f"{label} account_type is {doc.account_type}; expected Receivable.")
        return False

    add_item(items, "Pass", "Low", "Account Scope", key, label, f"{label} verified: {account}.", None, "Account", account)
    return True


def remittance_source_counts():
    counts = {
        "remittance_import_count": count_dt("NDIS Remittance Import"),
        "remittance_line_count": count_dt("NDIS Remittance Import Line"),
        "candidate_paid_line_count": 0,
        "candidate_short_paid_line_count": 0,
        "blocked_rejected_line_count": 0,
        "unmatched_line_count": 0,
    }
    if not frappe.db.exists("DocType", "NDIS Remittance Import Line"):
        return counts

    meta = frappe.get_meta("NDIS Remittance Import Line")
    fields = [df.fieldname for df in meta.fields]
    status_field = first_existing_field(fields, ["claim_outcome", "outcome", "payment_outcome", "status", "invoice_status", "match_status"])
    matched_field = first_existing_field(fields, ["claim_line", "matched_claim_line", "ndis_claim_line", "claim_line_reference", "reference_claim_line"])

    query_fields = ["name"]
    for field in [status_field, matched_field]:
        if field and field not in query_fields:
            query_fields.append(field)

    for row in frappe.get_all("NDIS Remittance Import Line", fields=query_fields, limit=5000):
        status_text = str(row.get(status_field) or "").strip().lower() if status_field else ""
        matched_value = row.get(matched_field) if matched_field else None
        if "short" in status_text and "paid" in status_text:
            counts["candidate_short_paid_line_count"] += 1
        elif status_text in ["paid", "fully paid"]:
            counts["candidate_paid_line_count"] += 1
        elif "reject" in status_text:
            counts["blocked_rejected_line_count"] += 1
        if matched_field and not matched_value:
            counts["unmatched_line_count"] += 1
    return counts


def first_existing_field(fields, candidates):
    for candidate in candidates:
        if candidate in fields:
            return candidate
    return None


def evaluate_source_readiness(items):
    counts = remittance_source_counts()
    if counts["remittance_import_count"] > 0:
        add_item(items, "Pass", "Low", "Source Readiness", "remittance_imports", "Remittance imports", f"{counts['remittance_import_count']} remittance import record(s) found.")
    else:
        add_item(items, "Warning", "Medium", "Source Readiness", "remittance_imports", "Remittance imports", "No remittance import records found. Phase 6A can approve design; Phase 6B preview will need source data.")

    if counts["remittance_line_count"] > 0:
        add_item(items, "Pass", "Low", "Source Readiness", "remittance_lines", "Remittance import lines", f"{counts['remittance_line_count']} remittance import line(s) found.")
    else:
        add_item(items, "Warning", "Medium", "Source Readiness", "remittance_lines", "Remittance import lines", "No remittance import lines found. Phase 6B preview may remain source-pending.")

    candidate_count = counts["candidate_paid_line_count"] + counts["candidate_short_paid_line_count"]
    if candidate_count:
        add_item(items, "Pass", "Low", "Source Readiness", "candidate_lines", "Paid/short-paid candidates", f"{candidate_count} possible candidate line(s) found.")
    else:
        add_item(items, "Info", "Low", "Source Readiness", "candidate_lines", "Paid/short-paid candidates", "No paid/short-paid candidate lines detected yet.")

    if counts["blocked_rejected_line_count"]:
        add_item(items, "Info", "Low", "Source Readiness", "rejected_lines", "Rejected lines", f"{counts['blocked_rejected_line_count']} rejected line(s) found; these will be blocked from PE posting.")
    else:
        add_item(items, "Pass", "Low", "Source Readiness", "rejected_lines", "Rejected lines", "No rejected lines detected in source scan.")
    return counts


def evaluate_policy_controls(items):
    live_enabled = count_dt("NDIS PE Production Posting Policy", {"production_posting_enabled": 1})
    if live_enabled:
        add_item(items, "Blocker", "Critical", "Policy Control", "live_enabled_policy", "Live-enabled posting policy", f"{live_enabled} live-enabled policy record(s) found.")
    else:
        add_item(items, "Pass", "Low", "Policy Control", "live_enabled_policy", "Live-enabled posting policy", "Zero live-enabled policy records.")
    return live_enabled


def evaluate_design_rules(items):
    rules = [
        ("single_company", "Single company only", "Future posting must be restricted to one company per run."),
        ("single_bank", "Single bank account only", "Future posting must use one approved bank account per run."),
        ("paid_short_paid_only", "Paid / Short Paid only", "Only Paid and Short Paid remittance lines may become Payment Entries."),
        ("reject_rejected", "Reject rejected claims", "Rejected claim lines must never create Payment Entries."),
        ("block_overpayment", "Block overpayment", "Allocated amount must not exceed invoice/outstanding/claim amount."),
        ("block_cross_company", "Block cross-company", "No cross-company Payment Entry references are allowed."),
        ("batch_cap", "Batch cap", "Future preview/posting must enforce line and amount caps."),
        ("no_auto_external", "No external movement", "No Xero, ABA, STP, payroll, email, or bank feed allocation in this pathway."),
    ]
    for key, label, detail in rules:
        add_item(items, "Pass", "Low", "Design Rule", key, label, detail)
    return len(rules)


def summarise_items(items):
    return {
        "blocker_count": len([i for i in items if i["status"] == "Blocker"]),
        "warning_count": len([i for i in items if i["status"] == "Warning"]),
        "pass_count": len([i for i in items if i["status"] == "Pass"]),
        "info_count": len([i for i in items if i["status"] == "Info"]),
        "item_count": len(items),
    }


def calculate_score(blockers, warnings):
    score = 100
    score -= int(blockers or 0) * 25
    score -= int(warnings or 0) * 5
    return max(0, round(score, 2))


def design_status(score, blockers, warnings, approved):
    if blockers:
        return "Blocked"
    if approved:
        return "Approved For Preview Phase"
    if warnings:
        return "Ready With Warnings"
    if score >= 95:
        return "Ready For Preview Design"
    return "Needs Review"


def create_gate_items(doc, items):
    for item in items:
        row = frappe.new_doc(ITEM_DOCTYPE)
        row.design_gate = doc.name
        row.status = item["status"]
        row.severity = item["severity"]
        row.category = item["category"]
        row.check_key = item["check_key"]
        row.check_label = item["check_label"]
        row.detail = item["detail"]
        row.recommendation = item.get("recommendation")
        row.source_doctype = item.get("source_doctype")
        row.source_name = item.get("source_name")
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_real_remittance_pe_design_gate(
    company=DEFAULT_COMPANY,
    bank_account=DEFAULT_BANK_ACCOUNT,
    receivable_account=DEFAULT_RECEIVABLE_ACCOUNT,
    batch_line_cap=10,
    batch_amount_cap=10000,
    acknowledgement=None,
    dry_run=1,
    notes=None,
):
    assert_action("run_real_remittance_pe_design_gate")
    dry_run = int(dry_run or 0)
    items = []
    guard_before = guardrails()

    config = evaluate_config(items)
    freeze = evaluate_phase5k(items)
    evaluate_accounts(items, company, bank_account, receivable_account)
    source_counts = evaluate_source_readiness(items)
    live_enabled_policy_count = evaluate_policy_controls(items)
    evaluate_design_rules(items)

    if int(batch_line_cap or 0) <= 0:
        add_item(items, "Blocker", "Critical", "Batch Control", "batch_line_cap", "Batch line cap", "Batch line cap must be positive.")
    else:
        add_item(items, "Pass", "Low", "Batch Control", "batch_line_cap", "Batch line cap", f"Future batch line cap set to {int(batch_line_cap)}.")

    if flt(batch_amount_cap) <= 0:
        add_item(items, "Blocker", "Critical", "Batch Control", "batch_amount_cap", "Batch amount cap", "Batch amount cap must be positive.")
    else:
        add_item(items, "Pass", "Low", "Batch Control", "batch_amount_cap", "Batch amount cap", f"Future batch amount cap set to {flt(batch_amount_cap):.2f}.")

    ack_ok = acknowledgement == DESIGN_ACK
    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "design_ack", "Design acknowledgement", "Exact acknowledgement supplied.")
    elif dry_run:
        add_item(
            items,
            "Info",
            "Low",
            "Acknowledgement",
            "design_ack",
            "Design acknowledgement",
            f"Required acknowledgement for approval: {DESIGN_ACK}",
        )
    else:
        add_item(
            items,
            "Warning",
            "Medium",
            "Acknowledgement",
            "design_ack",
            "Design acknowledgement",
            f"Required acknowledgement not supplied. Required: {DESIGN_ACK}",
            "Provide exact acknowledgement to approve Phase 6B preview design.",
        )

    summary = summarise_items(items)
    score = calculate_score(summary["blocker_count"], summary["warning_count"])
    approved = int(ack_ok and summary["blocker_count"] == 0)
    status = "Approved" if approved else ("Blocked" if summary["blocker_count"] else ("Previewed" if dry_run else "Needs Review"))
    guard_after = guardrails()

    result = {
        "dry_run": bool(dry_run),
        "status": status,
        "design_status": design_status(score, summary["blocker_count"], summary["warning_count"], approved),
        "design_score": score,
        "design_approved_for_preview_phase": approved,
        "real_posting_allowed": 0,
        "company": company,
        "bank_account": bank_account,
        "receivable_account": receivable_account,
        "allowed_outcomes": "Paid, Short Paid",
        "blocked_outcomes": "Rejected, Duplicate, Overpayment, Cross-company, Unmatched",
        "batch_line_cap": int(batch_line_cap or 10),
        "batch_amount_cap": flt(batch_amount_cap),
        "phase5k_freeze": freeze.name if freeze else None,
        "phase5j_rollback_run": freeze.phase5j_rollback_run if freeze else None,
        "phase5i_run": freeze.phase5i_run if freeze else None,
        "source_counts": source_counts,
        "live_enabled_policy_count": live_enabled_policy_count,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "config": config,
        "required_acknowledgement": DESIGN_ACK,
        "acknowledgement_ok": ack_ok,
        "summary": summary,
        "items": items,
        "note": "Phase 6A is design-only. No Payment Entry, GL Entry, invoice, allocation, Xero, ABA, STP, payroll, or email movement is created.",
    }

    if dry_run:
        return result

    doc = frappe.new_doc(GATE_DOCTYPE)
    doc.design_gate_id = make_gate_id()
    doc.status = result["status"]
    doc.gate_type = "Limited Real Remittance To Payment Entry"
    doc.design_approved_for_preview_phase = approved
    doc.real_posting_allowed = 0
    doc.company = company
    doc.bank_account = bank_account
    doc.receivable_account = receivable_account
    doc.payer_scope = "Single NDIS payer/remittance import only"
    doc.allowed_outcomes = result["allowed_outcomes"]
    doc.blocked_outcomes = result["blocked_outcomes"]
    doc.batch_line_cap = int(batch_line_cap or 10)
    doc.batch_amount_cap = flt(batch_amount_cap)
    doc.phase5k_freeze = result["phase5k_freeze"]
    doc.phase5j_rollback_run = result["phase5j_rollback_run"]
    doc.phase5i_run = result["phase5i_run"]
    for key, value in source_counts.items():
        setattr(doc, key, value)
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.design_score = score
    doc.design_status = result["design_status"]
    doc.blocker_count = summary["blocker_count"]
    doc.warning_count = summary["warning_count"]
    doc.pass_count = summary["pass_count"]
    doc.info_count = summary["info_count"]
    doc.item_count = summary["item_count"]
    doc.payment_entry_count_before = guard_before["payment_entry_count"]
    doc.payment_entry_count_after = guard_after["payment_entry_count"]
    doc.payment_entry_gl_count = guard_before["payment_entry_gl_count"]
    doc.gl_entry_count_today = guard_before["gl_entry_count_today"]
    doc.submitted_journal_entry_count_today = guard_before["submitted_journal_entry_count_today"]
    doc.sales_invoice_count_today = guard_before["sales_invoice_count_today"]
    doc.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
    doc.live_enabled_policy_count = live_enabled_policy_count
    doc.required_acknowledgement = DESIGN_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_gate_items(doc, items)

    guard_after = guardrails()
    result["guardrails_after"] = guard_after
    frappe.db.set_value(
        GATE_DOCTYPE,
        doc.name,
        {
            "payment_entry_count_after": guard_after["payment_entry_count"],
            "summary_json": safe_json(result),
        },
        update_modified=False,
    )
    frappe.db.commit()

    result["created"] = True
    result["design_gate"] = doc.name
    result["design_gate_id"] = doc.design_gate_id
    return result


@frappe.whitelist()
def cancel_real_remittance_pe_design_gate(design_gate, reason=None):
    assert_action("cancel_real_remittance_pe_design_gate")
    if not frappe.db.exists(GATE_DOCTYPE, design_gate):
        frappe.throw(_("Design gate not found: {0}").format(design_gate))
    doc = frappe.get_doc(GATE_DOCTYPE, design_gate)
    if doc.status == "Approved":
        frappe.throw(_("Approved Phase 6A design gate cannot be cancelled. Create a superseding design gate if required."))

    frappe.db.set_value(
        GATE_DOCTYPE,
        design_gate,
        {
            "status": "Cancelled",
            "design_approved_for_preview_phase": 0,
            "real_posting_allowed": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 6A design gate cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        f"""
        UPDATE `tab{ITEM_DOCTYPE}`
        SET status = 'Cancelled'
        WHERE design_gate = %(design_gate)s
        """,
        {"design_gate": design_gate},
    )
    frappe.db.commit()
    return {
        "design_gate": design_gate,
        "status": "Cancelled",
        "note": "Design gate cancelled only. No accounting movement occurred.",
    }


@frappe.whitelist()
def quick_real_remittance_pe_design_gate_summary(limit=20):
    gates = frappe.get_all(
        GATE_DOCTYPE,
        fields=[
            "name",
            "design_gate_id",
            "status",
            "design_status",
            "design_score",
            "design_approved_for_preview_phase",
            "real_posting_allowed",
            "company",
            "bank_account",
            "receivable_account",
            "candidate_paid_line_count",
            "candidate_short_paid_line_count",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        ITEM_DOCTYPE,
        fields=[
            "name",
            "design_gate",
            "status",
            "severity",
            "category",
            "check_label",
            "detail",
            "recommendation",
            "source_doctype",
            "source_name",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "gates": gates,
        "items": items,
        "required_acknowledgement": DESIGN_ACK,
        "source_counts": remittance_source_counts(),
        "guardrails": guardrails(),
        "config": config_state(),
        "note": "Phase 6A summary only. No accounting movement is performed.",
    }


def execute_gate_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("status"):
        conditions.append("g.status = %(status)s")
        params["status"] = filters.get("status")
    if filters.get("from_date"):
        conditions.append("DATE(g.checked_on) >= %(from_date)s")
        params["from_date"] = filters.get("from_date")
    if filters.get("to_date"):
        conditions.append("DATE(g.checked_on) <= %(to_date)s")
        params["to_date"] = filters.get("to_date")

    columns = [
        {"fieldname": "design_gate", "label": _("Design Gate"), "fieldtype": "Link", "options": GATE_DOCTYPE, "width": 220},
        {"fieldname": "design_gate_id", "label": _("Gate ID"), "fieldtype": "Data", "width": 360},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "design_status", "label": _("Design Status"), "fieldtype": "Data", "width": 220},
        {"fieldname": "design_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "design_approved_for_preview_phase", "label": _("Approved For Preview"), "fieldtype": "Check", "width": 150},
        {"fieldname": "real_posting_allowed", "label": _("Real Posting Allowed"), "fieldtype": "Check", "width": 150},
        {"fieldname": "candidate_paid_line_count", "label": _("Paid Candidates"), "fieldtype": "Int", "width": 120},
        {"fieldname": "candidate_short_paid_line_count", "label": _("Short Paid Candidates"), "fieldtype": "Int", "width": 150},
        {"fieldname": "payment_entry_count_before", "label": _("PE Count Before"), "fieldtype": "Int", "width": 120},
        {"fieldname": "payment_entry_count_after", "label": _("PE Count After"), "fieldtype": "Int", "width": 120},
        {"fieldname": "payment_entry_gl_count", "label": _("PE GL Count"), "fieldtype": "Int", "width": 110},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            g.name AS design_gate,
            g.design_gate_id,
            g.status,
            g.design_status,
            g.design_score,
            g.design_approved_for_preview_phase,
            g.real_posting_allowed,
            g.candidate_paid_line_count,
            g.candidate_short_paid_line_count,
            g.payment_entry_count_before,
            g.payment_entry_count_after,
            g.payment_entry_gl_count,
            g.checked_on
        FROM `tab{GATE_DOCTYPE}` g
        {build_where(conditions)}
        ORDER BY g.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.design_gate_id for row in data[:20]],
            "datasets": [
                {"name": "Approved", "values": [int(row.design_approved_for_preview_phase or 0) for row in data[:20]]},
                {"name": "Real Posting Allowed", "values": [int(row.real_posting_allowed or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Design Gates"), "datatype": "Int"},
        {"value": sum(int(row.design_approved_for_preview_phase or 0) for row in data), "indicator": "Green", "label": _("Approved For Preview"), "datatype": "Int"},
        {"value": sum(int(row.real_posting_allowed or 0) for row in data), "indicator": "Red", "label": _("Real Posting Allowed"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_exception_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    for fieldname in ["design_gate", "status", "severity", "category"]:
        if filters.get(fieldname):
            conditions.append(f"i.{fieldname} = %({fieldname})s")
            params[fieldname] = filters.get(fieldname)

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": ITEM_DOCTYPE, "width": 220},
        {"fieldname": "design_gate", "label": _("Design Gate"), "fieldtype": "Link", "options": GATE_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 180},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 320},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 460},
        {"fieldname": "recommendation", "label": _("Recommendation"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 180},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Data", "width": 220},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item,
            i.design_gate,
            i.status,
            i.severity,
            i.category,
            i.check_label,
            i.detail,
            i.recommendation,
            i.source_doctype,
            i.source_name,
            i.checked_on
        FROM `tab{ITEM_DOCTYPE}` i
        {build_where(conditions)}
        ORDER BY
            CASE i.status
                WHEN 'Blocker' THEN 1
                WHEN 'Warning' THEN 2
                WHEN 'Info' THEN 3
                WHEN 'Pass' THEN 4
                ELSE 5
            END,
            i.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart_map = {}
    for row in data:
        key = row.status or "Info"
        chart_map[key] = chart_map.get(key, 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Items", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Items"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Pass"]), "indicator": "Green", "label": _("Pass"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Warning"]), "indicator": "Orange", "label": _("Warnings"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_source_readiness_report(filters=None):
    columns = [
        {"fieldname": "doctype", "label": _("Source Type"), "fieldtype": "Data", "width": 180},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Dynamic Link", "options": "doctype", "width": 220},
        {"fieldname": "status", "label": _("Status / Outcome"), "fieldtype": "Data", "width": 180},
        {"fieldname": "matched_claim_line", "label": _("Matched Claim Line"), "fieldtype": "Data", "width": 220},
        {"fieldname": "readiness", "label": _("Readiness"), "fieldtype": "Data", "width": 220},
        {"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = []
    if not frappe.db.exists("DocType", "NDIS Remittance Import Line"):
        return columns, data, None, {"data": {"labels": [], "datasets": []}, "type": "bar"}, []

    meta = frappe.get_meta("NDIS Remittance Import Line")
    fieldnames = [df.fieldname for df in meta.fields]
    status_field = first_existing_field(fieldnames, ["claim_outcome", "outcome", "payment_outcome", "status", "invoice_status", "match_status"])
    matched_field = first_existing_field(fieldnames, ["claim_line", "matched_claim_line", "ndis_claim_line", "claim_line_reference", "reference_claim_line"])
    amount_field = first_existing_field(fieldnames, ["paid_amount", "payment_amount", "amount", "received_amount", "allocated_amount"])
    fields = ["name"]
    for field in [status_field, matched_field, amount_field]:
        if field and field not in fields:
            fields.append(field)

    for row in frappe.get_all("NDIS Remittance Import Line", fields=fields, order_by="creation desc", limit=500):
        status_text = str(row.get(status_field) or "") if status_field else ""
        matched_value = row.get(matched_field) if matched_field else None
        data.append(
            {
                "doctype": "NDIS Remittance Import Line",
                "source_name": row.name,
                "status": status_text,
                "matched_claim_line": matched_value,
                "readiness": classify_readiness(status_text, matched_value),
                "amount": flt(row.get(amount_field) or 0) if amount_field else 0,
                "currency": currency(),
            }
        )

    chart_map = {}
    for row in data:
        chart_map[row["readiness"]] = chart_map.get(row["readiness"], 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Lines", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Remittance Lines"), "datatype": "Int"},
        {"value": len([r for r in data if r["readiness"] == "Candidate: Paid/Short Paid"]), "indicator": "Green", "label": _("Candidates"), "datatype": "Int"},
        {"value": len([r for r in data if r["readiness"].startswith("Blocked")]), "indicator": "Red", "label": _("Blocked"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def classify_readiness(status_text, matched_value):
    text = str(status_text or "").lower()
    if not matched_value:
        return "Blocked: Unmatched"
    if "reject" in text:
        return "Blocked: Rejected"
    if "short" in text and "paid" in text:
        return "Candidate: Paid/Short Paid"
    if text in ["paid", "fully paid"]:
        return "Candidate: Paid/Short Paid"
    return "Review Required"


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
