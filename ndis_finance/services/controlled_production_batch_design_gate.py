import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


DESIGN_ACK = "I_CONFIRM_PHASE8A_CONTROLLED_PRODUCTION_BATCH_DESIGN_ONLY_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
GATE_DOCTYPE = "NDIS Controlled Production Batch Design Gate"
ITEM_DOCTYPE = "NDIS Controlled Production Batch Design Gate Item"

DEFAULT_POLICIES = [
    {"policy_id": "PHASE8A-ELIGIBLE-PAID", "policy_name": "Allow matched Paid remittance lines only", "policy_type": "Eligibility", "allow_paid": 1, "allow_short_paid": 0},
    {"policy_id": "PHASE8A-ELIGIBLE-SHORT-PAID", "policy_name": "Allow matched Short Paid remittance lines with shortfall preserved", "policy_type": "Eligibility", "allow_paid": 0, "allow_short_paid": 1},
    {"policy_id": "PHASE8A-BLOCK-REJECTED", "policy_name": "Block rejected remittance lines", "policy_type": "Safety Guardrail", "allow_rejected": 0},
    {"policy_id": "PHASE8A-BLOCK-UNMATCHED", "policy_name": "Block unmatched remittance lines", "policy_type": "Safety Guardrail", "allow_unmatched": 0},
    {"policy_id": "PHASE8A-BLOCK-DUPLICATE-OVERPAYMENT", "policy_name": "Block duplicate invoice allocations and overpayments", "policy_type": "Safety Guardrail", "allow_duplicate_invoice": 0, "allow_overpayment": 0},
    {"policy_id": "PHASE8A-BLOCK-CROSS-COMPANY", "policy_name": "Block cross-company posting", "policy_type": "Safety Guardrail", "allow_cross_company": 0},
    {"policy_id": "PHASE8A-CAP-FIRST-PRODUCTION-BATCH", "policy_name": "First controlled production batch cap", "policy_type": "Batch Cap", "max_batch_lines": 3, "max_batch_amount": 3},
    {"policy_id": "PHASE8A-REQUIRE-PREVIEW-ACK-ROLLBACK-FREEZE", "policy_name": "Require preview, CFO acknowledgement, rollback path and freeze", "policy_type": "Rollback Requirement", "requires_preview_before_posting": 1, "requires_cfo_acknowledgement": 1, "requires_immediate_rollback_path": 1, "requires_freeze_after_rollback": 1},
]


def make_design_gate_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-CTRL-PROD-BATCH-DESIGN-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
        "batch_live_enabled_policy_count": count_dt(POLICY_DOCTYPE, {"production_batch_enabled": 1}),
        "production_live_enabled_policy_count": count_dt(POLICY_DOCTYPE, {"live_posting_allowed": 1}),
    }


def latest_phase7h_freeze():
    rows = frappe.get_all(
        "NDIS Real Remittance Batch PE Evidence Freeze",
        filters={
            "status": "Frozen",
            "evidence_freeze_allowed": 1,
            "ready_for_next_phase": 1,
            "batch_posting_allowed": 0,
            "real_posting_allowed": 0,
        },
        fields=[
            "name",
            "freeze_id",
            "rollback_run",
            "smoke_run",
            "source_run",
            "company",
            "payment_entry",
            "payment_entry_docstatus_after_rollback",
            "submitted_tagged_pe_count",
            "cancelled_tagged_pe_count",
            "invoice_outstanding_after_rollback_total",
            "source_invoice_restored_count",
            "payment_entry_gl_net_after_rollback",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return frappe._dict(rows[0]) if rows else None


def get_company_accounts(company):
    bank = None
    receivable = None
    known_bank = "11510 - Every Day Bank Account - CHCPL"
    known_receivable = "12010 - Trade Debtors - CHCPL"
    if company and frappe.db.exists("Account", known_bank) and frappe.db.get_value("Account", known_bank, "company") == company:
        bank = known_bank
    if company and frappe.db.exists("Account", known_receivable) and frappe.db.get_value("Account", known_receivable, "company") == company:
        receivable = known_receivable
    if company and not bank:
        bank = frappe.db.get_value("Account", {"company": company, "account_type": ["in", ["Bank", "Cash"]], "is_group": 0, "disabled": 0}, "name")
    if company and not receivable:
        receivable = frappe.db.get_value("Account", {"company": company, "account_type": "Receivable", "is_group": 0, "disabled": 0}, "name")
    return bank, receivable


def seed_default_policies():
    freeze = latest_phase7h_freeze()
    company = (freeze.company if freeze else None) or frappe.defaults.get_global_default("company") or frappe.db.get_value("Company", {}, "name")
    bank, receivable = get_company_accounts(company)
    created = 0
    updated = 0
    for item in DEFAULT_POLICIES:
        existing = frappe.db.exists(POLICY_DOCTYPE, {"policy_id": item["policy_id"]})
        doc = frappe.get_doc(POLICY_DOCTYPE, existing) if existing else frappe.new_doc(POLICY_DOCTYPE)
        if existing:
            updated += 1
        else:
            doc.policy_id = item["policy_id"]
            created += 1
        doc.policy_name = item["policy_name"]
        doc.status = "Active"
        doc.policy_type = item["policy_type"]
        doc.company = company
        doc.bank_account = bank
        doc.receivable_account = receivable
        doc.allow_paid = int(item.get("allow_paid", 1))
        doc.allow_short_paid = int(item.get("allow_short_paid", 1))
        doc.allow_rejected = int(item.get("allow_rejected", 0))
        doc.allow_unmatched = int(item.get("allow_unmatched", 0))
        doc.allow_duplicate_invoice = int(item.get("allow_duplicate_invoice", 0))
        doc.allow_overpayment = int(item.get("allow_overpayment", 0))
        doc.allow_cross_company = int(item.get("allow_cross_company", 0))
        doc.max_batch_lines = int(item.get("max_batch_lines", 3))
        doc.max_batch_amount = flt(item.get("max_batch_amount", 3))
        doc.single_payment_entry_only = 1
        doc.requires_preview_before_posting = int(item.get("requires_preview_before_posting", 1))
        doc.requires_cfo_acknowledgement = int(item.get("requires_cfo_acknowledgement", 1))
        doc.requires_immediate_rollback_path = int(item.get("requires_immediate_rollback_path", 1))
        doc.requires_freeze_after_rollback = int(item.get("requires_freeze_after_rollback", 1))
        doc.design_policy_only = 1
        doc.production_batch_enabled = 0
        doc.live_posting_allowed = 0
        doc.created_by_phase = "Phase 8A"
        doc.notes = "Phase 8A design-only policy. It must not enable live posting."
        doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"created": created, "updated": updated, "policy_count": count_dt(POLICY_DOCTYPE), "live_enabled_policy_count": count_dt(POLICY_DOCTYPE, {"production_batch_enabled": 1})}


def get_policy_rows():
    return frappe.get_all(
        POLICY_DOCTYPE,
        fields=[
            "name",
            "policy_id",
            "policy_name",
            "status",
            "policy_type",
            "company",
            "bank_account",
            "receivable_account",
            "allow_paid",
            "allow_short_paid",
            "allow_rejected",
            "allow_unmatched",
            "allow_duplicate_invoice",
            "allow_overpayment",
            "allow_cross_company",
            "max_batch_lines",
            "max_batch_amount",
            "single_payment_entry_only",
            "requires_preview_before_posting",
            "requires_cfo_acknowledgement",
            "requires_immediate_rollback_path",
            "requires_freeze_after_rollback",
            "design_policy_only",
            "production_batch_enabled",
            "live_posting_allowed",
        ],
        order_by="policy_id asc",
    )


def policy_summary():
    policies = get_policy_rows()
    active = [p for p in policies if p.status == "Active"]
    live = [p for p in policies if int(p.production_batch_enabled or 0) or int(p.live_posting_allowed or 0)]
    unsafe = []
    for p in policies:
        for fieldname, reason in [
            ("allow_rejected", "Rejected lines allowed"),
            ("allow_unmatched", "Unmatched lines allowed"),
            ("allow_duplicate_invoice", "Duplicate invoice allowed"),
            ("allow_overpayment", "Overpayment allowed"),
            ("allow_cross_company", "Cross-company allowed"),
        ]:
            if int(p.get(fieldname) or 0):
                unsafe.append((p, reason))
        if int(p.max_batch_lines or 0) > 3:
            unsafe.append((p, "Max batch lines above 3"))
        if flt(p.max_batch_amount or 0) > 3:
            unsafe.append((p, "Max batch amount above 3"))
    max_lines = min([int(p.max_batch_lines or 3) for p in policies] or [3])
    max_amount = min([flt(p.max_batch_amount or 3) for p in policies] or [3])
    company = next((p.company for p in policies if p.company), None)
    bank = next((p.bank_account for p in policies if p.bank_account), None)
    receivable = next((p.receivable_account for p in policies if p.receivable_account), None)
    return {
        "policies": policies,
        "policy_count": len(policies),
        "active_policy_count": len(active),
        "live_enabled_policy_count": len(live),
        "unsafe_policy_count": len(unsafe),
        "unsafe": unsafe,
        "max_batch_lines": max_lines,
        "max_batch_amount": max_amount,
        "company": company,
        "bank_account": bank,
        "receivable_account": receivable,
    }


def add_item(items, status, severity, category, check_key, check_label, detail, source_doctype=None, source_name=None):
    items.append({"status": status, "severity": severity, "category": category, "check_key": check_key, "check_label": check_label, "detail": detail, "source_doctype": source_doctype, "source_name": source_name})


def summarise_items(items):
    return {
        "blocker_count": len([i for i in items if i["status"] == "Blocker"]),
        "warning_count": len([i for i in items if i["status"] == "Warning"]),
        "pass_count": len([i for i in items if i["status"] == "Pass"]),
        "info_count": len([i for i in items if i["status"] == "Info"]),
        "item_count": len(items),
    }


def calculate_score(blockers, warnings):
    return max(0, round(100 - int(blockers or 0) * 25 - int(warnings or 0) * 5, 2))


def evaluate_design(freeze, policy_data, config, guard, ack_ok):
    items = []
    if not freeze:
        add_item(items, "Blocker", "Critical", "Phase 7H Evidence", "freeze_exists", "Phase 7H freeze exists", "No approved Phase 7H freeze found.")
        return items
    add_item(items, "Pass", "Low", "Phase 7H Evidence", "freeze_exists", "Phase 7H freeze exists", f"Freeze found: {freeze.freeze_id}.", "NDIS Real Remittance Batch PE Evidence Freeze", freeze.name)
    add_item(items, "Pass" if int(freeze.payment_entry_docstatus_after_rollback or 0) == 2 else "Blocker", "Low", "Rollback Evidence", "pe_cancelled", "Payment Entry cancelled", f"Payment Entry {freeze.payment_entry} docstatus is {freeze.payment_entry_docstatus_after_rollback}.", "Payment Entry", freeze.payment_entry)
    add_item(items, "Pass" if int(freeze.submitted_tagged_pe_count or 0) == 0 and int(freeze.cancelled_tagged_pe_count or 0) >= 1 else "Blocker", "Low", "Rollback Evidence", "tagged_pe_count", "Tagged PE count", "Submitted tagged PE is zero and cancelled tagged PE exists.")
    add_item(items, "Pass" if flt(freeze.invoice_outstanding_after_rollback_total or 0) > 0 and int(freeze.source_invoice_restored_count or 0) >= 1 else "Blocker", "Low", "Rollback Evidence", "invoice_restored", "Source invoices restored", f"Outstanding restored total {flt(freeze.invoice_outstanding_after_rollback_total, 2)}.")
    add_item(items, "Pass" if flt(freeze.payment_entry_gl_net_after_rollback or 0) == 0 else "Blocker", "Low", "GL Evidence", "pe_gl_balanced", "Payment Entry GL balanced", f"PE GL net {flt(freeze.payment_entry_gl_net_after_rollback, 2)}.")
    add_item(items, "Pass" if not config["production_mode"] else "Blocker", "Low" if not config["production_mode"] else "Critical", "Site Config", "production_mode", "Production mode", "Production mode remains disabled." if not config["production_mode"] else "Production mode is enabled.")
    add_item(items, "Pass" if not config["live_pe_enabled"] else "Blocker", "Low" if not config["live_pe_enabled"] else "Critical", "Site Config", "live_pe_enabled", "Live PE posting config", "Live PE posting remains disabled." if not config["live_pe_enabled"] else "Live PE posting config is enabled.")
    add_item(items, "Pass" if policy_data["policy_count"] >= len(DEFAULT_POLICIES) else "Blocker", "Low", "Policy Register", "policy_count", "Policy count", f"{policy_data['policy_count']} policy rows found.")
    add_item(items, "Pass" if policy_data["active_policy_count"] >= len(DEFAULT_POLICIES) else "Warning", "Low" if policy_data["active_policy_count"] >= len(DEFAULT_POLICIES) else "Medium", "Policy Register", "active_policy_count", "Active policy count", f"{policy_data['active_policy_count']} active policies.")
    add_item(items, "Pass" if policy_data["live_enabled_policy_count"] == 0 else "Blocker", "Low" if policy_data["live_enabled_policy_count"] == 0 else "Critical", "Policy Safety", "live_policy_zero", "Live policy disabled", f"{policy_data['live_enabled_policy_count']} live-enabled policy rows found.")
    if policy_data["unsafe_policy_count"] == 0:
        add_item(items, "Pass", "Low", "Policy Safety", "unsafe_policy_zero", "Unsafe policy count", "No unsafe policy flags found.")
    else:
        for policy, reason in policy_data["unsafe"]:
            add_item(items, "Blocker", "Critical", "Policy Safety", "unsafe_policy", "Unsafe policy flag", f"{policy.policy_id}: {reason}", POLICY_DOCTYPE, policy.name)
    add_item(items, "Pass" if int(policy_data["max_batch_lines"] or 0) <= 3 and flt(policy_data["max_batch_amount"] or 0) <= 3 else "Blocker", "Low", "Batch Cap", "cap_safe", "Batch cap safe", f"Cap {policy_data['max_batch_lines']} lines / {flt(policy_data['max_batch_amount'], 2)}.")
    add_item(items, "Pass", "Low", "Movement Guardrail", "movement_snapshot", "Movement snapshot", "Payment Entry and GL counts captured only.")
    add_item(items, "Pass" if guard["submitted_journal_entry_count_today"] == 0 else "Blocker", "Low" if guard["submitted_journal_entry_count_today"] == 0 else "Critical", "Movement Guardrail", "je_zero", "Submitted JE today", str(guard["submitted_journal_entry_count_today"]))
    add_item(items, "Pass" if guard["purchase_invoice_count_today"] == 0 else "Blocker", "Low" if guard["purchase_invoice_count_today"] == 0 else "Critical", "Movement Guardrail", "pi_zero", "Purchase Invoice today", str(guard["purchase_invoice_count_today"]))
    add_item(items, "Pass" if ack_ok else "Warning", "Low" if ack_ok else "Medium", "Acknowledgement", "design_ack", "Design acknowledgement", "Exact acknowledgement supplied." if ack_ok else f"Required acknowledgement not supplied: {DESIGN_ACK}")
    return items


def create_design_items(doc, items):
    for item in items:
        row = frappe.new_doc(ITEM_DOCTYPE)
        row.design_gate = doc.name
        row.status = item["status"]
        row.severity = item["severity"]
        row.category = item["category"]
        row.check_key = item["check_key"]
        row.check_label = item["check_label"]
        row.detail = item["detail"]
        row.source_doctype = item.get("source_doctype")
        row.source_name = item.get("source_name")
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_controlled_production_batch_design_gate(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_controlled_production_batch_design_gate")
    seed_default_policies()
    freeze = latest_phase7h_freeze()
    config = config_state()
    policy_data = policy_summary()
    guard_before = guardrails()
    ack_ok = acknowledgement == DESIGN_ACK
    items = evaluate_design(freeze, policy_data, config, guard_before, ack_ok)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    approved = int(ack_ok and item_summary["blocker_count"] == 0 and bool(freeze))
    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Approved" if approved else "Needs Review",
        "design_status": "Approved For Controlled Production Preview" if approved else "Needs Review",
        "design_approved_for_preview_phase": approved,
        "ready_for_controlled_production_preview": approved,
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "phase7h_freeze": freeze.name if freeze else None,
        "phase7g_rollback_run": freeze.rollback_run if freeze else None,
        "phase7f_smoke_run": freeze.smoke_run if freeze else None,
        "phase7e_source_run": freeze.source_run if freeze else None,
        "company": policy_data["company"] or (freeze.company if freeze else None),
        "bank_account": policy_data["bank_account"],
        "receivable_account": policy_data["receivable_account"],
        "max_batch_lines": policy_data["max_batch_lines"],
        "max_batch_amount": policy_data["max_batch_amount"],
        "policy_count": policy_data["policy_count"],
        "active_policy_count": policy_data["active_policy_count"],
        "live_enabled_policy_count": policy_data["live_enabled_policy_count"],
        "unsafe_policy_count": policy_data["unsafe_policy_count"],
        "actual_payment_entry_created_count": 0,
        "actual_gl_created_count": 0,
        "design_score": score,
        **item_summary,
        "items": items,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": DESIGN_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 8A is design-only. It creates no Payment Entry, GL Entry, Journal Entry, Purchase Invoice, or live posting policy.",
    }
    if int(dry_run or 0):
        return result

    doc = frappe.new_doc(GATE_DOCTYPE)
    doc.design_gate_id = make_design_gate_id()
    for fieldname in [
        "status",
        "design_status",
        "design_approved_for_preview_phase",
        "ready_for_controlled_production_preview",
        "production_batch_posting_allowed",
        "real_posting_allowed",
        "phase7h_freeze",
        "phase7g_rollback_run",
        "phase7f_smoke_run",
        "phase7e_source_run",
        "company",
        "bank_account",
        "receivable_account",
        "max_batch_lines",
        "max_batch_amount",
        "policy_count",
        "active_policy_count",
        "live_enabled_policy_count",
        "unsafe_policy_count",
        "actual_payment_entry_created_count",
        "actual_gl_created_count",
        "design_score",
        "blocker_count",
        "warning_count",
        "pass_count",
        "info_count",
        "item_count",
    ]:
        setattr(doc, fieldname, result.get(fieldname))
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.payment_entry_count_before = guard_before["payment_entry_count"]
    doc.payment_entry_count_after = guardrails()["payment_entry_count"]
    doc.payment_entry_gl_count_before = guard_before["payment_entry_gl_count"]
    doc.payment_entry_gl_count_after = guardrails()["payment_entry_gl_count"]
    doc.submitted_journal_entry_count_today = guard_before["submitted_journal_entry_count_today"]
    doc.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
    doc.required_acknowledgement = DESIGN_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_design_items(doc, items)
    guard_after = guardrails()
    frappe.db.set_value(GATE_DOCTYPE, doc.name, {"payment_entry_count_after": guard_after["payment_entry_count"], "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"], "summary_json": safe_json({**result, "guardrails_after": guard_after})}, update_modified=False)
    frappe.db.commit()
    result.update({"created": True, "design_gate": doc.name, "design_gate_id": doc.design_gate_id, "guardrails_after": guard_after})
    return result


@frappe.whitelist()
def cancel_controlled_production_batch_design_gate(design_gate, reason=None):
    assert_action("cancel_controlled_production_batch_design_gate")
    if not frappe.db.exists(GATE_DOCTYPE, design_gate):
        frappe.throw(_("Design gate not found: {0}").format(design_gate))
    doc = frappe.get_doc(GATE_DOCTYPE, design_gate)
    if doc.status == "Cancelled":
        return {"design_gate": design_gate, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.design_approved_for_preview_phase or 0):
        frappe.throw(_("Cannot cancel an approved design gate. Create a superseding design gate instead."))
    frappe.db.set_value(GATE_DOCTYPE, design_gate, {"status": "Cancelled", "design_status": "Cancelled", "design_approved_for_preview_phase": 0, "ready_for_controlled_production_preview": 0, "production_batch_posting_allowed": 0, "real_posting_allowed": 0, "cancelled_on": now_datetime(), "cancelled_by": frappe.session.user, "summary_json": reason or "Phase 8A design gate audit cancelled."}, update_modified=False)
    frappe.db.sql(f"UPDATE `tab{ITEM_DOCTYPE}` SET status = 'Cancelled' WHERE design_gate = %(design_gate)s", {"design_gate": design_gate})
    frappe.db.commit()
    return {"design_gate": design_gate, "status": "Cancelled", "note": "Design gate audit record cancelled only. No accounting movement occurred."}


@frappe.whitelist()
def quick_controlled_production_batch_design_summary(limit=20):
    gates = frappe.get_all(
        GATE_DOCTYPE,
        fields=["name", "design_gate_id", "status", "design_status", "design_approved_for_preview_phase", "ready_for_controlled_production_preview", "production_batch_posting_allowed", "real_posting_allowed", "phase7h_freeze", "company", "bank_account", "receivable_account", "max_batch_lines", "max_batch_amount", "policy_count", "active_policy_count", "live_enabled_policy_count", "unsafe_policy_count", "actual_payment_entry_created_count", "actual_gl_created_count", "design_score", "checked_on", "checked_by"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(ITEM_DOCTYPE, fields=["name", "design_gate", "status", "severity", "category", "check_label", "detail", "source_doctype", "source_name"], order_by="creation desc", limit=int(limit or 20))
    return {"gates": gates, "policies": get_policy_rows(), "items": items, "required_acknowledgement": DESIGN_ACK, "guardrails": guardrails(), "config": config_state(), "note": "Phase 8A design summary. Design-only; no posting enabled and no accounting movement."}


def execute_policy_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("p.status = %(status)s")
        params["status"] = filters.status
    if filters.get("policy_type"):
        conditions.append("p.policy_type = %(policy_type)s")
        params["policy_type"] = filters.policy_type
    columns = [
        {"fieldname": "policy", "label": _("Policy"), "fieldtype": "Link", "options": POLICY_DOCTYPE, "width": 220},
        {"fieldname": "policy_id", "label": _("Policy ID"), "fieldtype": "Data", "width": 260},
        {"fieldname": "policy_name", "label": _("Policy Name"), "fieldtype": "Data", "width": 380},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "policy_type", "label": _("Policy Type"), "fieldtype": "Data", "width": 160},
        {"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 220},
        {"fieldname": "max_batch_lines", "label": _("Max Lines"), "fieldtype": "Int", "width": 100},
        {"fieldname": "max_batch_amount", "label": _("Max Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "production_batch_enabled", "label": _("Production Enabled"), "fieldtype": "Check", "width": 140},
        {"fieldname": "live_posting_allowed", "label": _("Live Allowed"), "fieldtype": "Check", "width": 120},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(f"SELECT p.name AS policy, p.policy_id, p.policy_name, p.status, p.policy_type, p.company, p.max_batch_lines, p.max_batch_amount, p.production_batch_enabled, p.live_posting_allowed, %(currency)s AS currency FROM `tab{POLICY_DOCTYPE}` p {build_where(conditions)} ORDER BY p.policy_id ASC", params, as_dict=True)
    chart = {"data": {"labels": [row.policy_id for row in data], "datasets": [{"name": "Live Enabled", "values": [int(row.live_posting_allowed or 0) for row in data]}, {"name": "Production Enabled", "values": [int(row.production_batch_enabled or 0) for row in data]}]}, "type": "bar"}
    summary = [{"value": len(data), "indicator": "Blue", "label": _("Policies"), "datatype": "Int"}, {"value": sum(int(row.live_posting_allowed or 0) for row in data), "indicator": "Red", "label": _("Live Enabled"), "datatype": "Int"}, {"value": sum(int(row.production_batch_enabled or 0) for row in data), "indicator": "Red", "label": _("Production Enabled"), "datatype": "Int"}]
    return columns, data, None, chart, summary


def execute_design_gate_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("g.status = %(status)s")
        params["status"] = filters.status
    if filters.get("from_date"):
        conditions.append("DATE(g.checked_on) >= %(from_date)s")
        params["from_date"] = filters.from_date
    if filters.get("to_date"):
        conditions.append("DATE(g.checked_on) <= %(to_date)s")
        params["to_date"] = filters.to_date
    columns = [
        {"fieldname": "design_gate", "label": _("Design Gate"), "fieldtype": "Link", "options": GATE_DOCTYPE, "width": 220},
        {"fieldname": "design_gate_id", "label": _("Design Gate ID"), "fieldtype": "Data", "width": 390},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "design_status", "label": _("Design Status"), "fieldtype": "Data", "width": 300},
        {"fieldname": "ready_for_controlled_production_preview", "label": _("Ready Preview"), "fieldtype": "Check", "width": 120},
        {"fieldname": "production_batch_posting_allowed", "label": _("Production Posting Allowed"), "fieldtype": "Check", "width": 180},
        {"fieldname": "real_posting_allowed", "label": _("Real Posting Allowed"), "fieldtype": "Check", "width": 150},
        {"fieldname": "phase7h_freeze", "label": _("Phase 7H Freeze"), "fieldtype": "Link", "options": "NDIS Real Remittance Batch PE Evidence Freeze", "width": 220},
        {"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 220},
        {"fieldname": "max_batch_lines", "label": _("Max Lines"), "fieldtype": "Int", "width": 100},
        {"fieldname": "max_batch_amount", "label": _("Max Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "policy_count", "label": _("Policies"), "fieldtype": "Int", "width": 90},
        {"fieldname": "live_enabled_policy_count", "label": _("Live Policies"), "fieldtype": "Int", "width": 110},
        {"fieldname": "unsafe_policy_count", "label": _("Unsafe Policies"), "fieldtype": "Int", "width": 120},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 100},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 100},
        {"fieldname": "design_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(f"SELECT g.name AS design_gate, g.design_gate_id, g.status, g.design_status, g.ready_for_controlled_production_preview, g.production_batch_posting_allowed, g.real_posting_allowed, g.phase7h_freeze, g.company, g.max_batch_lines, g.max_batch_amount, g.policy_count, g.live_enabled_policy_count, g.unsafe_policy_count, g.actual_payment_entry_created_count, g.actual_gl_created_count, g.design_score, g.checked_on, %(currency)s AS currency FROM `tab{GATE_DOCTYPE}` g {build_where(conditions)} ORDER BY g.creation DESC", params, as_dict=True)
    chart = {"data": {"labels": [row.design_gate_id for row in data[:20]], "datasets": [{"name": "Ready Preview", "values": [int(row.ready_for_controlled_production_preview or 0) for row in data[:20]]}, {"name": "Actual PE", "values": [int(row.actual_payment_entry_created_count or 0) for row in data[:20]]}, {"name": "Actual GL", "values": [int(row.actual_gl_created_count or 0) for row in data[:20]]}]}, "type": "bar"}
    summary = [{"value": len(data), "indicator": "Blue", "label": _("Design Gates"), "datatype": "Int"}, {"value": sum(int(row.ready_for_controlled_production_preview or 0) for row in data), "indicator": "Green", "label": _("Ready Preview"), "datatype": "Int"}, {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE"), "datatype": "Int"}, {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL"), "datatype": "Int"}]
    return columns, data, None, chart, summary


def execute_design_exception_report(filters=None):
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
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 170},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 300},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 520},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 180},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Data", "width": 220},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    data = frappe.db.sql(f"SELECT i.name AS item, i.design_gate, i.status, i.severity, i.category, i.check_label, i.detail, i.source_doctype, i.source_name, i.checked_on FROM `tab{ITEM_DOCTYPE}` i {build_where(conditions)} ORDER BY CASE i.status WHEN 'Blocker' THEN 1 WHEN 'Warning' THEN 2 WHEN 'Info' THEN 3 WHEN 'Pass' THEN 4 ELSE 5 END, i.creation DESC", params, as_dict=True)
    chart_map = {}
    for row in data:
        chart_map[row.status or "Info"] = chart_map.get(row.status or "Info", 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Items", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [{"value": len(data), "indicator": "Blue", "label": _("Items"), "datatype": "Int"}, {"value": len([row for row in data if row.status == "Pass"]), "indicator": "Green", "label": _("Pass"), "datatype": "Int"}, {"value": len([row for row in data if row.status == "Warning"]), "indicator": "Orange", "label": _("Warnings"), "datatype": "Int"}, {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"}]
    return columns, data, None, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
