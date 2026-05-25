import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


DESIGN_ACK = "I_CONFIRM_PE_PRODUCTION_POSTING_DESIGN_REVIEWED_NO_LIVE_POSTING"

POLICY_DOCTYPE = "NDIS PE Production Posting Policy"
GATE_DOCTYPE = "NDIS PE Production Design Gate"
GATE_ITEM_DOCTYPE = "NDIS PE Production Design Gate Item"

PHASE_HEALTH_CHECKS = [
    ("Phase 5A", "ndis_finance.setup.phase5a.health_check"),
    ("Phase 4D", "ndis_finance.setup.phase4d.health_check"),
    ("Phase 4C", "ndis_finance.setup.phase4c.health_check"),
    ("Phase 4B", "ndis_finance.setup.phase4b.health_check"),
    ("Phase 4A", "ndis_finance.setup.phase4a.health_check"),
    ("Phase 3E", "ndis_finance.setup.phase3e.health_check"),
    ("Phase 3D", "ndis_finance.setup.phase3d.health_check"),
    ("Phase 3C", "ndis_finance.setup.phase3c.health_check"),
    ("Phase 3B", "ndis_finance.setup.phase3b.health_check"),
    ("Phase 3A", "ndis_finance.setup.phase3a.health_check"),
]


def make_gate_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-PE-PROD-DESIGN-{timestamp}-{frappe.generate_hash(length=5).upper()}"


def safe_json(value):
    try:
        return json.dumps(value, indent=2, default=str)
    except Exception:
        return str(value)


def contains_false_or_none(value):
    if value is False or value is None:
        return True
    if isinstance(value, dict):
        return any(contains_false_or_none(child) for child in value.values())
    if isinstance(value, list):
        return any(contains_false_or_none(child) for child in value)
    return False


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


def count_dt(doctype, filters=None):
    if not frappe.db.exists("DocType", doctype):
        return 0
    return frappe.db.count(doctype, filters or {})


def latest_doc(doctype, filters=None, fields=None, order_by="creation desc"):
    rows = frappe.get_all(doctype, filters=filters or {}, fields=fields or ["name"], order_by=order_by, limit=1)
    return rows[0] if rows else None


def evaluate_config(items):
    sandbox_enabled = int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0)
    production_mode = int(frappe.conf.get("ndis_finance_production_mode") or 0)
    live_pe_enabled = int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0)

    add_item(
        items,
        "Pass" if sandbox_enabled else "Warning",
        "Low" if sandbox_enabled else "Medium",
        "Site Config",
        "sandbox_enabled",
        "Sandbox config",
        "Sandbox posting config is enabled." if sandbox_enabled else "Sandbox posting config is not enabled.",
    )

    if production_mode:
        add_item(items, "Blocker", "Critical", "Site Config", "production_mode", "Production mode", "Production mode is enabled.", "Phase 5A must not run with production mode enabled.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "production_mode", "Production mode", "Production mode is disabled.")

    if live_pe_enabled:
        add_item(items, "Blocker", "Critical", "Site Config", "live_pe_posting", "Live Payment Entry posting config", "Live Payment Entry posting config is enabled.", "Disable ndis_finance_live_payment_entry_posting_enabled before Phase 5A.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "live_pe_posting", "Live Payment Entry posting config", "Live Payment Entry posting config is disabled.")

    return sandbox_enabled, production_mode, live_pe_enabled


def evaluate_health(items):
    for label, method_path in PHASE_HEALTH_CHECKS:
        try:
            result = frappe.get_attr(method_path)()
            if contains_false_or_none(result):
                add_item(items, "Blocker", "Critical", "Regression Health", method_path, f"{label} health check", "Health check returned false/null values.", "Fix the phase health check before approving production posting design.")
            else:
                add_item(items, "Pass", "Low", "Regression Health", method_path, f"{label} health check", "Health check is green.")
        except Exception as exc:
            add_item(items, "Blocker", "Critical", "Regression Health", method_path, f"{label} health check", f"Health check failed: {str(exc)}", "Fix the failed health check before proceeding.")


def evaluate_readiness(items):
    phase4d_freeze_count = count_dt("NDIS PE Sandbox Readiness Freeze")
    phase4d_ready_count = count_dt(
        "NDIS PE Sandbox Readiness Freeze",
        {"readiness_allowed": 1, "ready_for_next_design_phase": 1, "blocker_count": 0},
    )
    invoice_backed_smoke_count = count_dt("NDIS Invoice Backed PE Smoke Run", {"status": "Completed"})
    cleanup_pack_count = count_dt("NDIS Sandbox Accounting Cleanup Pack", {"status": "Cleaned"})

    latest_freeze = latest_doc(
        "NDIS PE Sandbox Readiness Freeze",
        {"readiness_allowed": 1, "ready_for_next_design_phase": 1, "blocker_count": 0},
        ["name", "freeze_id", "readiness_score"],
        "frozen_on desc, creation desc",
    )

    if phase4d_ready_count:
        add_item(items, "Pass", "Low", "Readiness Evidence", "phase4d_ready", "Phase 4D readiness freeze", f"{phase4d_ready_count} approved Phase 4D readiness freeze record(s) found.", None, "NDIS PE Sandbox Readiness Freeze", latest_freeze.name if latest_freeze else None)
    else:
        add_item(items, "Blocker", "Critical", "Readiness Evidence", "phase4d_ready", "Phase 4D readiness freeze", "No approved Phase 4D readiness freeze found.", "Complete Phase 4D before Phase 5A.")

    if invoice_backed_smoke_count:
        add_item(items, "Pass", "Low", "Readiness Evidence", "invoice_backed_smoke", "Invoice-backed PE smoke", f"{invoice_backed_smoke_count} completed invoice-backed PE smoke run(s) found.")
    else:
        add_item(items, "Blocker", "Critical", "Readiness Evidence", "invoice_backed_smoke", "Invoice-backed PE smoke", "No completed Phase 4B smoke run found.")

    if cleanup_pack_count:
        add_item(items, "Pass", "Low", "Readiness Evidence", "cleanup_pack", "Sandbox cleanup pack", f"{cleanup_pack_count} cleaned sandbox accounting cleanup pack(s) found.")
    else:
        add_item(items, "Blocker", "Critical", "Readiness Evidence", "cleanup_pack", "Sandbox cleanup pack", "No cleaned Phase 4C cleanup pack found.")

    return {
        "phase4d_freeze_count": phase4d_freeze_count,
        "phase4d_ready_count": phase4d_ready_count,
        "invoice_backed_smoke_count": invoice_backed_smoke_count,
        "cleanup_pack_count": cleanup_pack_count,
    }


def evaluate_policies(items):
    policy_count = count_dt(POLICY_DOCTYPE)
    design_approved_policy_count = count_dt(POLICY_DOCTYPE, {"policy_status": "Design Approved"})
    needs_review_policy_count = count_dt(POLICY_DOCTYPE, {"policy_status": "Needs Review"})
    blocked_policy_count = count_dt(POLICY_DOCTYPE, {"policy_status": "Blocked"})
    live_enabled_policy_count = count_dt(POLICY_DOCTYPE, {"production_posting_enabled": 1})
    paid_policy_count = count_dt(POLICY_DOCTYPE, {"event_type": "Paid Claim"})
    short_paid_policy_count = count_dt(POLICY_DOCTYPE, {"event_type": "Short Paid Claim"})
    rejected_block_policy_count = count_dt(POLICY_DOCTYPE, {"event_type": "Rejected Claim", "posting_decision": "Never Post Payment Entry"})

    if policy_count >= 7:
        add_item(items, "Pass", "Low", "Policy Register", "policy_count", "Production posting policy count", f"{policy_count} production policy record(s) found.")
    else:
        add_item(items, "Blocker", "Critical", "Policy Register", "policy_count", "Production posting policy count", f"Only {policy_count} policy record(s) found.", "Run Phase 5A installer to seed default policies.")

    if live_enabled_policy_count:
        add_item(items, "Blocker", "Critical", "Policy Register", "live_enabled_policy", "Live-enabled policies", f"{live_enabled_policy_count} policy record(s) have production_posting_enabled = 1.", "Phase 5A must keep all live posting disabled.")
    else:
        add_item(items, "Pass", "Low", "Policy Register", "live_enabled_policy", "Live-enabled policies", "No policy has live production posting enabled.")

    add_item(items, "Pass" if paid_policy_count else "Blocker", "Low" if paid_policy_count else "Critical", "Policy Register", "paid_policy", "Paid claim policy", "Paid claim posting policy exists." if paid_policy_count else "Paid claim posting policy is missing.")
    add_item(items, "Pass" if short_paid_policy_count else "Blocker", "Low" if short_paid_policy_count else "Critical", "Policy Register", "short_paid_policy", "Short-paid claim policy", "Short-paid claim posting policy exists." if short_paid_policy_count else "Short-paid claim posting policy is missing.")

    if rejected_block_policy_count:
        add_item(items, "Pass", "Low", "Policy Register", "rejected_policy", "Rejected claim block policy", "Rejected claim policy blocks Payment Entry creation.")
    else:
        add_item(items, "Blocker", "Critical", "Policy Register", "rejected_policy", "Rejected claim block policy", "Rejected claim no-posting policy is missing.")

    if needs_review_policy_count:
        add_item(items, "Warning", "Medium", "Policy Register", "needs_review_policy", "Policies needing review", f"{needs_review_policy_count} policy record(s) need review.", "Review before live activation phase.")
    else:
        add_item(items, "Pass", "Low", "Policy Register", "needs_review_policy", "Policies needing review", "No policy currently needs review.")

    if blocked_policy_count:
        add_item(items, "Warning", "Medium", "Policy Register", "blocked_policy", "Blocked policies", f"{blocked_policy_count} policy record(s) are blocked.", "This is acceptable for policies that intentionally block posting.")
    else:
        add_item(items, "Info", "Low", "Policy Register", "blocked_policy", "Blocked policies", "No policies marked blocked.")

    return {
        "policy_count": policy_count,
        "design_approved_policy_count": design_approved_policy_count,
        "needs_review_policy_count": needs_review_policy_count,
        "blocked_policy_count": blocked_policy_count,
        "live_enabled_policy_count": live_enabled_policy_count,
        "paid_policy_count": paid_policy_count,
        "short_paid_policy_count": short_paid_policy_count,
        "rejected_block_policy_count": rejected_block_policy_count,
    }


def evaluate_policy_account_controls(items):
    rows = frappe.get_all(
        POLICY_DOCTYPE,
        fields=["name", "policy_id", "event_type", "posting_decision", "mapping_rule", "allowed_bank_account", "allowed_receivable_account"],
        limit=10000,
    )
    eligible_rows = [row for row in rows if row.posting_decision == "Eligible After Approval" and row.event_type in ["Paid Claim", "Short Paid Claim"]]

    for row in eligible_rows:
        if row.mapping_rule:
            add_item(items, "Pass", "Low", "Policy Mapping", f"mapping_{row.policy_id}", f"Mapping rule for {row.policy_id}", f"Mapping rule is set to {row.mapping_rule}.", None, POLICY_DOCTYPE, row.name)
        else:
            add_item(items, "Warning", "Medium", "Policy Mapping", f"mapping_{row.policy_id}", f"Mapping rule for {row.policy_id}", "Mapping rule is not set.", "Set mapping rule before production activation.", POLICY_DOCTYPE, row.name)

        if row.allowed_bank_account and row.allowed_receivable_account:
            add_item(items, "Pass", "Low", "Account Control", f"accounts_{row.policy_id}", f"Account controls for {row.policy_id}", "Allowed bank and receivable accounts are explicitly set.", None, POLICY_DOCTYPE, row.name)
        else:
            add_item(items, "Warning", "High", "Account Control", f"accounts_{row.policy_id}", f"Account controls for {row.policy_id}", "Allowed bank and/or receivable account is not yet set.", "Set allowed accounts before live activation. This warning is acceptable in Phase 5A design stage.", POLICY_DOCTYPE, row.name)


def evaluate_guardrails(items):
    draft_sandbox_pe_count = count_dt("Payment Entry", {"custom_ndis_sandbox_payment_entry_draft_only": 1, "docstatus": 0})
    submitted_sandbox_pe_count = count_dt("Payment Entry", {"custom_ndis_sandbox_payment_entry_draft_only": 1, "docstatus": 1})
    payment_entry_gl_count = count_dt("GL Entry", {"voucher_type": "Payment Entry"}) if frappe.db.exists("DocType", "GL Entry") else 0
    submitted_pe_today = count_dt("Payment Entry", {"creation": [">=", today()], "docstatus": 1})
    submitted_je_today = count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}) if frappe.db.exists("DocType", "Journal Entry") else 0
    purchase_invoice_today = count_dt("Purchase Invoice", {"creation": [">=", today()]}) if frappe.db.exists("DocType", "Purchase Invoice") else 0

    checks = [
        (draft_sandbox_pe_count, "draft_sandbox_pe", "Draft sandbox Payment Entries", "draft sandbox PE record(s) remain.", "No draft sandbox Payment Entries remain."),
        (submitted_sandbox_pe_count, "submitted_sandbox_pe", "Submitted sandbox Payment Entries", "submitted sandbox PE record(s) found.", "No submitted sandbox Payment Entries found."),
        (payment_entry_gl_count, "payment_entry_gl", "Payment Entry GL", "Payment Entry GL record(s) found.", "No Payment Entry GL exists."),
        (submitted_pe_today, "submitted_pe_today", "Submitted Payment Entries today", "submitted Payment Entry record(s) today.", "No submitted Payment Entry today."),
        (submitted_je_today, "submitted_je_today", "Submitted Journal Entries today", "submitted Journal Entry record(s) today.", "No submitted Journal Entry today."),
        (purchase_invoice_today, "purchase_invoice_today", "Purchase Invoices today", "Purchase Invoice record(s) today.", "No Purchase Invoice today."),
    ]
    for count, key, label, fail_detail, pass_detail in checks:
        if count:
            add_item(items, "Blocker", "Critical", "Guardrail", key, label, f"{count} {fail_detail}", "Phase 5A must not create or tolerate this movement.")
        else:
            add_item(items, "Pass", "Low", "Guardrail", key, label, pass_detail)

    return {
        "draft_sandbox_pe_count": draft_sandbox_pe_count,
        "submitted_sandbox_pe_count": submitted_sandbox_pe_count,
        "payment_entry_gl_count": payment_entry_gl_count,
        "submitted_payment_entry_count_today": submitted_pe_today,
        "submitted_journal_entry_count_today": submitted_je_today,
        "purchase_invoice_count_today": purchase_invoice_today,
    }


def summarise_items(items):
    return {
        "blocker_count": len([item for item in items if item["status"] == "Blocker"]),
        "warning_count": len([item for item in items if item["status"] == "Warning"]),
        "pass_count": len([item for item in items if item["status"] == "Pass"]),
        "info_count": len([item for item in items if item["status"] == "Info"]),
        "item_count": len(items),
    }


def calculate_score(blockers, warnings):
    return max(0, round(100 - int(blockers or 0) * 25 - int(warnings or 0) * 5, 2))


def design_status(score, blockers, warnings):
    if blockers:
        return "Blocked"
    if warnings:
        return "Ready With Warnings"
    if score >= 95:
        return "Ready For Controlled Activation Design"
    return "Needs Review"


@frappe.whitelist()
def run_pe_production_design_gate(gate_type="Production Payment Entry Posting Design", acknowledgement=None, dry_run=0, notes=None):
    assert_action("run_pe_production_design_gate")

    items = []
    sandbox_enabled, production_mode, live_pe_enabled = evaluate_config(items)
    evaluate_health(items)
    readiness = evaluate_readiness(items)
    policies = evaluate_policies(items)
    evaluate_policy_account_controls(items)
    guardrails = evaluate_guardrails(items)

    ack_ok = acknowledgement == DESIGN_ACK
    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "design_ack", "Production PE design acknowledgement", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "design_ack", "Production PE design acknowledgement", f"Required acknowledgement not supplied. Required: {DESIGN_ACK}", "Provide exact acknowledgement to approve design for next phase.")

    summary = summarise_items(items)
    score = calculate_score(summary["blocker_count"], summary["warning_count"])
    final_design_status = design_status(score, summary["blocker_count"], summary["warning_count"])
    design_approved = int(summary["blocker_count"] == 0 and ack_ok)
    live_posting_allowed = 0

    if summary["blocker_count"]:
        status = "Blocked"
    elif not ack_ok or summary["warning_count"]:
        status = "Needs Review"
    else:
        status = "Design Approved"

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "gate_type": gate_type,
        "status": status,
        "design_approved_for_next_phase": design_approved,
        "live_posting_allowed": live_posting_allowed,
        "design_score": score,
        "design_status": final_design_status,
        "required_acknowledgement": DESIGN_ACK,
        "acknowledgement_ok": ack_ok,
        "summary": summary,
        "policies": policies,
        "readiness": readiness,
        "guardrails": guardrails,
        "items": items,
        "note": "Production Payment Entry design gate only. Live posting remains blocked. No Payment Entry, Journal Entry, GL Entry, Sales Invoice or Purchase Invoice is created.",
    }

    if int(dry_run or 0):
        return result

    doc = frappe.new_doc(GATE_DOCTYPE)
    doc.gate_id = make_gate_id()
    doc.status = status
    doc.gate_type = gate_type
    doc.design_approved_for_next_phase = design_approved
    doc.live_posting_allowed = live_posting_allowed
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = sandbox_enabled
    doc.production_mode_detected = production_mode
    doc.live_payment_entry_posting_config = live_pe_enabled
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.design_score = score
    doc.design_status = final_design_status
    doc.blocker_count = summary["blocker_count"]
    doc.warning_count = summary["warning_count"]
    doc.pass_count = summary["pass_count"]
    doc.info_count = summary["info_count"]
    doc.item_count = summary["item_count"]

    for fieldname, value in policies.items():
        setattr(doc, fieldname, value)
    for fieldname, value in readiness.items():
        setattr(doc, fieldname, value)
    for fieldname, value in guardrails.items():
        setattr(doc, fieldname, value)

    doc.required_acknowledgement = DESIGN_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    for item in items:
        row = frappe.new_doc(GATE_ITEM_DOCTYPE)
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

    frappe.db.commit()

    result["created"] = True
    result["design_gate"] = doc.name
    result["gate_id"] = doc.gate_id
    return result


@frappe.whitelist()
def cancel_pe_production_design_gate(design_gate, reason=None):
    assert_action("cancel_pe_production_design_gate")

    if not frappe.db.exists(GATE_DOCTYPE, design_gate):
        frappe.throw(_("PE Production Design Gate not found: {0}").format(design_gate))

    frappe.db.set_value(
        GATE_DOCTYPE,
        design_gate,
        {
            "status": "Cancelled",
            "design_approved_for_next_phase": 0,
            "live_posting_allowed": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Production Payment Entry design gate cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{GATE_ITEM_DOCTYPE}` SET status = 'Cancelled' WHERE design_gate = %(design_gate)s", {"design_gate": design_gate})
    frappe.db.commit()
    return {"design_gate": design_gate, "status": "Cancelled", "note": "Design gate cancelled only. No accounting/payment records were changed."}


@frappe.whitelist()
def quick_pe_production_design_summary(limit=20):
    gates = frappe.get_all(
        GATE_DOCTYPE,
        fields=[
            "name",
            "gate_id",
            "status",
            "design_approved_for_next_phase",
            "live_posting_allowed",
            "design_score",
            "design_status",
            "blocker_count",
            "warning_count",
            "policy_count",
            "live_enabled_policy_count",
            "draft_sandbox_pe_count",
            "submitted_sandbox_pe_count",
            "payment_entry_gl_count",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    policies = frappe.get_all(
        POLICY_DOCTYPE,
        fields=["name", "policy_id", "policy_name", "policy_status", "event_type", "posting_decision", "posting_mode", "production_posting_enabled", "mapping_rule", "approval_level"],
        order_by="policy_id asc",
        limit=100,
    )
    items = frappe.get_all(
        GATE_ITEM_DOCTYPE,
        fields=["name", "design_gate", "status", "severity", "category", "check_label", "detail", "recommendation", "source_doctype", "source_name"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {"gates": gates, "policies": policies, "items": items, "required_acknowledgement": DESIGN_ACK, "note": "Production PE design summary only. Live posting remains blocked."}


def execute_policy_register(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("policy_status"):
        conditions.append("p.policy_status = %(policy_status)s")
        params["policy_status"] = filters.policy_status
    if filters.get("event_type"):
        conditions.append("p.event_type = %(event_type)s")
        params["event_type"] = filters.event_type
    if filters.get("production_posting_enabled") not in [None, ""]:
        conditions.append("p.production_posting_enabled = %(production_posting_enabled)s")
        params["production_posting_enabled"] = int(filters.production_posting_enabled)

    columns = [
        {"fieldname": "policy", "label": _("Policy"), "fieldtype": "Link", "options": POLICY_DOCTYPE, "width": 220},
        {"fieldname": "policy_id", "label": _("Policy ID"), "fieldtype": "Data", "width": 260},
        {"fieldname": "policy_name", "label": _("Policy Name"), "fieldtype": "Data", "width": 280},
        {"fieldname": "policy_status", "label": _("Status"), "fieldtype": "Data", "width": 130},
        {"fieldname": "event_type", "label": _("Event Type"), "fieldtype": "Data", "width": 150},
        {"fieldname": "claim_outcome", "label": _("Outcome"), "fieldtype": "Data", "width": 120},
        {"fieldname": "posting_decision", "label": _("Posting Decision"), "fieldtype": "Data", "width": 210},
        {"fieldname": "posting_mode", "label": _("Posting Mode"), "fieldtype": "Data", "width": 230},
        {"fieldname": "production_posting_enabled", "label": _("Live Enabled"), "fieldtype": "Check", "width": 100},
        {"fieldname": "mapping_rule", "label": _("Mapping Rule"), "fieldtype": "Link", "options": "NDIS Payment Entry Mapping Rule", "width": 210},
        {"fieldname": "approval_level", "label": _("Approval"), "fieldtype": "Data", "width": 180},
        {"fieldname": "allowed_bank_account", "label": _("Bank Account"), "fieldtype": "Link", "options": "Account", "width": 210},
        {"fieldname": "allowed_receivable_account", "label": _("Receivable"), "fieldtype": "Link", "options": "Account", "width": 210},
    ]
    data = frappe.db.sql(
        f"""
        SELECT p.name AS policy, p.policy_id, p.policy_name, p.policy_status, p.event_type,
            p.claim_outcome, p.posting_decision, p.posting_mode, p.production_posting_enabled,
            p.mapping_rule, p.approval_level, p.allowed_bank_account, p.allowed_receivable_account
        FROM `tab{POLICY_DOCTYPE}` p
        {build_where(conditions)}
        ORDER BY p.policy_id ASC
        """,
        params,
        as_dict=True,
    )
    chart_map = {}
    for row in data:
        chart_map[row.policy_status or "Unknown"] = chart_map.get(row.policy_status or "Unknown", 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Policies", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Policies"), "datatype": "Int"},
        {"value": len([row for row in data if row.policy_status == "Design Approved"]), "indicator": "Green", "label": _("Design Approved"), "datatype": "Int"},
        {"value": len([row for row in data if row.production_posting_enabled]), "indicator": "Red", "label": _("Live Enabled"), "datatype": "Int"},
        {"value": len([row for row in data if row.policy_status == "Needs Review"]), "indicator": "Orange", "label": _("Needs Review"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_design_gate_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("status"):
        conditions.append("g.status = %(status)s")
        params["status"] = filters.status
    if filters.get("design_status"):
        conditions.append("g.design_status = %(design_status)s")
        params["design_status"] = filters.design_status
    if filters.get("from_date"):
        conditions.append("DATE(g.checked_on) >= %(from_date)s")
        params["from_date"] = filters.from_date
    if filters.get("to_date"):
        conditions.append("DATE(g.checked_on) <= %(to_date)s")
        params["to_date"] = filters.to_date

    columns = [
        {"fieldname": "design_gate", "label": _("Design Gate"), "fieldtype": "Link", "options": GATE_DOCTYPE, "width": 220},
        {"fieldname": "gate_id", "label": _("Gate ID"), "fieldtype": "Data", "width": 320},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 130},
        {"fieldname": "design_approved_for_next_phase", "label": _("Next Phase"), "fieldtype": "Check", "width": 100},
        {"fieldname": "live_posting_allowed", "label": _("Live Allowed"), "fieldtype": "Check", "width": 100},
        {"fieldname": "design_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "design_status", "label": _("Design Status"), "fieldtype": "Data", "width": 240},
        {"fieldname": "blocker_count", "label": _("Blockers"), "fieldtype": "Int", "width": 90},
        {"fieldname": "warning_count", "label": _("Warnings"), "fieldtype": "Int", "width": 90},
        {"fieldname": "policy_count", "label": _("Policies"), "fieldtype": "Int", "width": 90},
        {"fieldname": "live_enabled_policy_count", "label": _("Live Policies"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count", "label": _("PE GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    data = frappe.db.sql(
        f"""
        SELECT g.name AS design_gate, g.gate_id, g.status, g.design_approved_for_next_phase,
            g.live_posting_allowed, g.design_score, g.design_status, g.blocker_count,
            g.warning_count, g.policy_count, g.live_enabled_policy_count, g.payment_entry_gl_count,
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
            "labels": [row.gate_id for row in data[:20]],
            "datasets": [
                {"name": "Score", "values": [flt(row.design_score) for row in data[:20]]},
                {"name": "Blockers", "values": [int(row.blocker_count or 0) for row in data[:20]]},
                {"name": "Warnings", "values": [int(row.warning_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Design Gates"), "datatype": "Int"},
        {"value": len([row for row in data if row.design_approved_for_next_phase]), "indicator": "Green", "label": _("Next Phase Approved"), "datatype": "Int"},
        {"value": len([row for row in data if row.live_posting_allowed]), "indicator": "Red", "label": _("Live Allowed"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Blocked"]), "indicator": "Red", "label": _("Blocked"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_design_exception_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("design_gate"):
        conditions.append("i.design_gate = %(design_gate)s")
        params["design_gate"] = filters.design_gate
    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.status
    if filters.get("severity"):
        conditions.append("i.severity = %(severity)s")
        params["severity"] = filters.severity
    if filters.get("category"):
        conditions.append("i.category = %(category)s")
        params["category"] = filters.category

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": GATE_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "design_gate", "label": _("Design Gate"), "fieldtype": "Link", "options": GATE_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 180},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 300},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 430},
        {"fieldname": "recommendation", "label": _("Recommendation"), "fieldtype": "Small Text", "width": 430},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 180},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Data", "width": 220},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    data = frappe.db.sql(
        f"""
        SELECT i.name AS item, i.design_gate, i.status, i.severity, i.category, i.check_label,
            i.detail, i.recommendation, i.source_doctype, i.source_name, i.checked_on
        FROM `tab{GATE_ITEM_DOCTYPE}` i
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
        chart_map[row.status or "Info"] = chart_map.get(row.status or "Info", 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Items", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Items"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Pass"]), "indicator": "Green", "label": _("Pass"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Warning"]), "indicator": "Orange", "label": _("Warnings"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
