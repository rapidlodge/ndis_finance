import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


CLOSEOUT_ACK = "I_CONFIRM_PHASE10Z_CLOSE_GOVERNED_LIMITED_OPERATION_CYCLE_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
FREEZE_DOCTYPE = "NDIS Governed Limited Op Freeze"
CLOSEOUT_DOCTYPE = "NDIS Governed Limited Op Closeout"
CLOSEOUT_ITEM_DOCTYPE = "NDIS Governed Limited Op Closeout Item"


def make_closeout_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-GOVERNED-LIMITED-OP-CLOSEOUT-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def has_column(doctype, fieldname):
    try:
        return bool(frappe.db.has_column(doctype, fieldname))
    except Exception:
        return False


def get_value_if_has(doctype, name, fieldname, default=None):
    if not name or not frappe.db.exists(doctype, name) or not has_column(doctype, fieldname):
        return default
    value = frappe.db.get_value(doctype, name, fieldname)
    return default if value is None else value


def get_flag(doctype, name, fieldname, default=0):
    return int(get_value_if_has(doctype, name, fieldname, default) or 0)


def production_batch_enabled_policy_count():
    if not frappe.db.exists("DocType", POLICY_DOCTYPE) or not has_column(POLICY_DOCTYPE, "production_batch_enabled"):
        return 0
    return count_dt(POLICY_DOCTYPE, {"production_batch_enabled": 1})


def live_posting_allowed_policy_count():
    if not frappe.db.exists("DocType", POLICY_DOCTYPE) or not has_column(POLICY_DOCTYPE, "live_posting_allowed"):
        return 0
    return count_dt(POLICY_DOCTYPE, {"live_posting_allowed": 1})


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
        "production_batch_enabled_policy_count": production_batch_enabled_policy_count(),
        "live_posting_allowed_policy_count": live_posting_allowed_policy_count(),
    }


def latest_freeze():
    rows = frappe.get_all(
        FREEZE_DOCTYPE,
        filters={
            "status": "Frozen",
            "freeze_status": "Governed Limited Operation Smoke Rollback Evidence Frozen",
            "freeze_completed": 1,
            "ready_for_governed_limited_operation_closeout": 1,
            "payment_entry_cancelled_verified": 1,
            "invoice_outstanding_restored_verified": 1,
            "gl_net_zero_verified": 1,
            "no_new_accounting_movement_verified": 1,
            "policy_state_preserved_verified": 1,
            "policy_mutation_performed": 0,
            "actual_policy_mutation_count": 0,
            "payment_entry_docstatus": 2,
            "payment_entry_status": "Cancelled",
            "payment_entry_reference_count": 3,
            "voucher_gl_row_count": 8,
            "voucher_gl_net_balance": 0,
            "gl_account_non_zero_count": 0,
            "payment_entry_count_after": 8,
            "payment_entry_gl_count_after": 46,
            "actual_payment_entry_created_count": 0,
            "actual_payment_entry_cancelled_count": 0,
            "actual_gl_created_count": 0,
            "submitted_journal_entry_count_today": 0,
            "purchase_invoice_count_today": 0,
        },
        fields=[
            "name",
            "freeze_id",
            "rollback",
            "smoke",
            "execution_gate",
            "preview",
            "pre_execution_gate",
            "readiness",
            "governance_closeout",
            "freeze",
            "simulation",
            "runtime_watch",
            "baseline",
            "monitoring_register",
            "target_policy",
            "target_policy_name",
            "payment_entry",
            "payment_entry_docstatus",
            "payment_entry_status",
            "payment_entry_amount",
            "payment_entry_reference_count",
            "invoice_outstanding_restored_amount",
            "voucher_gl_row_count",
            "voucher_gl_net_balance",
            "gl_account_non_zero_count",
            "payment_entry_count_after",
            "payment_entry_gl_count_after",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_approved_closeout(freeze):
    rows = frappe.get_all(
        CLOSEOUT_DOCTYPE,
        filters={"freeze": freeze, "closeout_approved": 1, "governed_limited_operation_cycle_closed": 1},
        fields=["name", "closeout_id"],
        limit=1,
    )
    return rows[0] if rows else None


def payment_entry_reference_count(payment_entry):
    return count_dt("Payment Entry Reference", {"parent": payment_entry, "reference_doctype": "Sales Invoice"})


def voucher_gl_row_count(payment_entry):
    return count_dt("GL Entry", {"voucher_type": "Payment Entry", "voucher_no": payment_entry})


def voucher_gl_net_balance(payment_entry):
    value = frappe.db.sql(
        """
        SELECT ROUND(COALESCE(SUM(debit - credit), 0), 2)
        FROM `tabGL Entry`
        WHERE voucher_type='Payment Entry'
          AND voucher_no=%(payment_entry)s
        """,
        {"payment_entry": payment_entry},
    )[0][0]
    return flt(value or 0, 2)


def voucher_gl_non_zero_account_count(payment_entry):
    rows = frappe.db.sql(
        """
        SELECT account, ROUND(COALESCE(SUM(debit - credit), 0), 2) AS balance
        FROM `tabGL Entry`
        WHERE voucher_type='Payment Entry'
          AND voucher_no=%(payment_entry)s
        GROUP BY account
        HAVING ABS(balance) > 0.0001
        """,
        {"payment_entry": payment_entry},
        as_dict=True,
    )
    return len(rows)


def validate_closeout_source(freeze, guard, policy_enabled, policy_live, config):
    issues = []

    if not freeze:
        return ["No frozen Phase 10Y governed limited operation evidence found."]

    existing = existing_approved_closeout(freeze.name)
    if existing:
        issues.append(f"Approved Phase 10Z closeout already exists for this freeze: {existing.closeout_id}")

    required_links = {
        "freeze": (FREEZE_DOCTYPE, freeze.name),
        "rollback": ("NDIS Governed Limited Op Rollback", freeze.rollback),
        "smoke": ("NDIS Governed Limited Op Smoke", freeze.smoke),
        "execution_gate": ("NDIS Governed Limited Op Exec Gate", freeze.execution_gate),
        "preview": ("NDIS Governed Limited Op Preview", freeze.preview),
        "payment_entry": ("Payment Entry", freeze.payment_entry),
        "target_policy": (POLICY_DOCTYPE, freeze.target_policy),
    }
    for label, (doctype, name) in required_links.items():
        if not name:
            issues.append(f"Missing evidence link: {label}")
        elif not frappe.db.exists(doctype, name):
            issues.append(f"Linked evidence does not exist: {doctype} {name}")

    if not freeze.payment_entry or not frappe.db.exists("Payment Entry", freeze.payment_entry):
        return issues

    pe = frappe.get_doc("Payment Entry", freeze.payment_entry)
    if pe.docstatus != 2:
        issues.append(f"Payment Entry must remain cancelled. docstatus={pe.docstatus}")
    if pe.status != "Cancelled":
        issues.append(f"Payment Entry status must remain Cancelled. status={pe.status}")
    if flt(pe.paid_amount or pe.received_amount or 0, 2) != 3:
        issues.append("Payment Entry amount must remain 3.00.")
    if payment_entry_reference_count(pe.name) != 3:
        issues.append("Payment Entry Sales Invoice reference count must remain 3.")
    if voucher_gl_row_count(pe.name) != int(freeze.voucher_gl_row_count or 0):
        issues.append("Voucher GL row count no longer matches Phase 10Y freeze evidence.")
    if voucher_gl_net_balance(pe.name) != 0:
        issues.append("Voucher GL net balance must remain 0.00.")
    if voucher_gl_non_zero_account_count(pe.name) != 0:
        issues.append("Voucher GL account non-zero count must remain 0.")
    if flt(freeze.invoice_outstanding_restored_amount or 0, 2) != 3:
        issues.append("Invoice outstanding restored amount must remain 3.00.")
    if policy_enabled != 1:
        issues.append("Target policy production_batch_enabled must remain 1. Phase 10Z must not repair this.")
    if policy_live != 0:
        issues.append("Target policy live_posting_allowed must remain 0. Phase 10Z must not repair this.")
    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must remain enabled.")
    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0.")
    if guard["payment_entry_count"] != int(freeze.payment_entry_count_after or 0):
        issues.append("Current Payment Entry count must match Phase 10Y freeze after-count.")
    if guard["payment_entry_gl_count"] != int(freeze.payment_entry_gl_count_after or 0):
        issues.append("Current Payment Entry GL count must match Phase 10Y freeze after-count.")
    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry count today must remain 0.")
    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice count today must remain 0.")
    if int(config["sandbox_enabled"]) != 1:
        issues.append("Sandbox config must be 1.")
    if int(config["production_mode"]) != 0:
        issues.append("Production mode config must remain 0.")
    if int(config["live_pe_enabled"]) != 0:
        issues.append("Live Payment Entry posting config must remain 0.")
    return issues


def add_item(items, status, severity, category, check_key, check_label, detail, source_doctype=None, source_name=None):
    items.append(
        {
            "status": status,
            "severity": severity,
            "category": category,
            "check_key": check_key,
            "check_label": check_label,
            "detail": detail,
            "source_doctype": source_doctype,
            "source_name": source_name,
        }
    )


def build_items(freeze, issues, ack_ok, no_new_movement, policy_preserved):
    items = []
    if freeze:
        add_item(items, "Pass", "Low", "Evidence", "phase10y_freeze_exists", "Phase 10Y freeze exists", f"Freeze found: {freeze.freeze_id}.", FREEZE_DOCTYPE, freeze.name)
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase10y_freeze_exists", "Phase 10Y freeze exists", "No frozen Phase 10Y evidence found.")

    if issues:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Closeout Source", "closeout_source_valid", "Closeout source valid", issue)
    else:
        add_item(items, "Pass", "Critical", "Closeout Source", "closeout_source_valid", "Closeout source valid", "Phase 10S-10Y evidence is frozen and internally consistent.")

    checks = [
        ("payment_entry_cancelled", "Payment Entry remains cancelled", getattr(freeze, "payment_entry", None)),
        ("gl_net_zero", "Voucher GL net remains zero", getattr(freeze, "voucher_gl_net_balance", None)),
        ("invoice_restored", "Invoice outstanding remains restored", getattr(freeze, "invoice_outstanding_restored_amount", None)),
        ("no_new_movement", "Closeout creates no accounting movement", no_new_movement),
        ("policy_preserved", "Policy state remains 1 / 0", policy_preserved),
        ("steady_state_ready", "Ready for governed steady state continuation", int(bool(freeze) and not issues)),
    ]
    for key, label, value in checks:
        add_item(items, "Pass" if value or value == 0 else "Blocker", "High", "Closeout Verification", key, label, f"value={value}")

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {CLOSEOUT_ACK}")
    return items


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


def assign_if_has(doc, values):
    for fieldname, value in values.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)


def create_items(doc, items):
    for item in items:
        row = frappe.new_doc(CLOSEOUT_ITEM_DOCTYPE)
        row.closeout = doc.name
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
def run_governed_limited_operation_closeout(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_governed_limited_operation_closeout")

    freeze = latest_freeze()
    guard_before = guardrails()
    config = config_state()
    ack_ok = acknowledgement == CLOSEOUT_ACK

    policy_enabled_before = get_flag(POLICY_DOCTYPE, freeze.target_policy, "production_batch_enabled") if freeze else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, freeze.target_policy, "live_posting_allowed") if freeze else 0
    issues = validate_closeout_source(freeze, guard_before, policy_enabled_before, policy_live_before, config)
    guard_after = guardrails()
    policy_enabled_after = get_flag(POLICY_DOCTYPE, freeze.target_policy, "production_batch_enabled") if freeze else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, freeze.target_policy, "live_posting_allowed") if freeze else 0

    no_new_movement = int(guard_before == guard_after)
    policy_preserved = int(
        policy_enabled_before == 1
        and policy_enabled_after == 1
        and policy_live_before == 0
        and policy_live_after == 0
        and guard_before["production_batch_enabled_policy_count"] == guard_after["production_batch_enabled_policy_count"]
        and guard_before["live_posting_allowed_policy_count"] == guard_after["live_posting_allowed_policy_count"]
    )
    if not no_new_movement:
        issues.append("Accounting movement changed while preparing Phase 10Z closeout evidence.")
    if not policy_preserved:
        issues.append("Policy state changed while preparing Phase 10Z closeout evidence.")

    items = build_items(freeze, issues, ack_ok, no_new_movement, policy_preserved)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and freeze and no_new_movement and policy_preserved)

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Closeout Approved" if allowed else "Needs Review",
        "closeout_status": "Governed Limited Operation Cycle Closed" if allowed else "Needs Review",
        "closeout_approved": allowed,
        "governed_limited_operation_cycle_closed": allowed,
        "smoke_and_rollback_evidence_frozen_verified": 1 if freeze else 0,
        "payment_entry_cancelled_verified": 1 if freeze else 0,
        "invoice_outstanding_restored_verified": 1 if freeze else 0,
        "gl_net_zero_verified": 1 if freeze else 0,
        "no_new_accounting_movement_verified": no_new_movement,
        "policy_state_preserved_verified": policy_preserved,
        "ready_for_governed_steady_state_continuation": allowed,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": 0,
        "phase10y_freeze_verified": 1 if freeze else 0,
        "phase10x_rollback_verified": 1 if freeze else 0,
        "phase10w_smoke_verified": 1 if freeze else 0,
        "phase10v_execution_gate_verified": 1 if freeze else 0,
        "phase10u_preview_verified": 1 if freeze else 0,
        "phase10t_pre_execution_verified": 1 if freeze else 0,
        "phase10s_readiness_verified": 1 if freeze else 0,
        "phase10r_governance_closeout_verified": 1 if freeze else 0,
        "phase10q_freeze_verified": 1 if freeze else 0,
        "phase10p_simulation_verified": 1 if freeze else 0,
        "phase10o_runtime_watch_verified": 1 if freeze else 0,
        "phase10n_baseline_verified": 1 if freeze else 0,
        "controlled_policy_enabled_verified": int(policy_enabled_after == 1),
        "live_posting_blocked_verified": int(policy_live_after == 0),
        "freeze": freeze.name if freeze else None,
        "rollback": freeze.rollback if freeze else None,
        "smoke": freeze.smoke if freeze else None,
        "execution_gate": freeze.execution_gate if freeze else None,
        "preview": freeze.preview if freeze else None,
        "pre_execution_gate": freeze.pre_execution_gate if freeze else None,
        "readiness": freeze.readiness if freeze else None,
        "governance_closeout": freeze.governance_closeout if freeze else None,
        "runtime_watch": freeze.runtime_watch if freeze else None,
        "baseline": freeze.baseline if freeze else None,
        "monitoring_register": freeze.monitoring_register if freeze else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": freeze.target_policy if freeze else None,
        "target_policy_name": freeze.target_policy_name if freeze else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "production_batch_enabled_policy_count_before": guard_before["production_batch_enabled_policy_count"],
        "production_batch_enabled_policy_count_after": guard_after["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count_before": guard_before["live_posting_allowed_policy_count"],
        "live_posting_allowed_policy_count_after": guard_after["live_posting_allowed_policy_count"],
        "payment_entry": freeze.payment_entry if freeze else None,
        "payment_entry_docstatus": int(freeze.payment_entry_docstatus or 0) if freeze else 0,
        "payment_entry_status": freeze.payment_entry_status if freeze else None,
        "payment_entry_amount": flt(freeze.payment_entry_amount or 0, 2) if freeze else 0,
        "payment_entry_reference_count": int(freeze.payment_entry_reference_count or 0) if freeze else 0,
        "invoice_outstanding_restored_amount": flt(freeze.invoice_outstanding_restored_amount or 0, 2) if freeze else 0,
        "voucher_gl_row_count": int(freeze.voucher_gl_row_count or 0) if freeze else 0,
        "voucher_gl_net_balance": flt(freeze.voucher_gl_net_balance or 0, 2) if freeze else 0,
        "gl_account_non_zero_count": int(freeze.gl_account_non_zero_count or 0) if freeze else 0,
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "actual_payment_entry_created_count": 0,
        "actual_payment_entry_cancelled_count": 0,
        "actual_gl_created_count": 0,
        "submitted_journal_entry_count_today": guard_after["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_after["purchase_invoice_count_today"],
        "closeout_score": score,
        **item_summary,
        "items": items,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "required_acknowledgement": CLOSEOUT_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 10Z closes the governed limited operation cycle only. No Payment Entry, GL Entry, Journal Entry, Purchase Invoice, or policy mutation is performed.",
    }

    if int(dry_run or 0):
        result.update(
            {
                "status": "Needs Review",
                "closeout_status": "Needs Review",
                "closeout_approved": 0,
                "governed_limited_operation_cycle_closed": 0,
                "ready_for_governed_steady_state_continuation": 0,
            }
        )
        return result

    doc = frappe.new_doc(CLOSEOUT_DOCTYPE)
    doc.closeout_id = make_closeout_id()
    assign_if_has(doc, result)
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = CLOSEOUT_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.closeout_json = safe_json({"freeze": freeze, "guardrails_before": guard_before, "guardrails_after": guard_after, "issues": issues, "config": config})
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_items(doc, items)
    frappe.db.commit()
    return {**result, "created": True, "closeout": doc.name, "closeout_id": doc.closeout_id, "guardrails_after": guardrails()}


@frappe.whitelist()
def cancel_governed_limited_operation_closeout_audit(closeout, reason=None):
    assert_action("cancel_governed_limited_operation_closeout_audit")

    if not frappe.db.exists(CLOSEOUT_DOCTYPE, closeout):
        frappe.throw(_("Phase 10Z closeout audit not found: {0}").format(closeout))

    doc = frappe.get_doc(CLOSEOUT_DOCTYPE, closeout)
    if doc.status == "Cancelled":
        return {"closeout": closeout, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.closeout_approved or 0):
        frappe.throw(_("Approved Phase 10Z closeout cannot be cancelled."))

    frappe.db.set_value(
        CLOSEOUT_DOCTYPE,
        closeout,
        {
            "status": "Cancelled",
            "closeout_status": "Cancelled",
            "closeout_approved": 0,
            "governed_limited_operation_cycle_closed": 0,
            "ready_for_governed_steady_state_continuation": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 10Z no-ack closeout audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        """
        UPDATE `tabNDIS Governed Limited Op Closeout Item`
        SET status='Cancelled'
        WHERE closeout=%(closeout)s
        """,
        {"closeout": closeout},
    )
    frappe.db.commit()
    return {"closeout": closeout, "status": "Cancelled", "note": "Audit-only closeout cancelled. No accounting movement occurred."}


@frappe.whitelist()
def quick_governed_limited_operation_closeout_summary(limit=20):
    closeouts = frappe.get_all(
        CLOSEOUT_DOCTYPE,
        fields=[
            "name",
            "closeout_id",
            "status",
            "closeout_status",
            "closeout_approved",
            "governed_limited_operation_cycle_closed",
            "ready_for_governed_steady_state_continuation",
            "freeze",
            "payment_entry",
            "payment_entry_docstatus",
            "payment_entry_status",
            "payment_entry_count_after",
            "payment_entry_gl_count_after",
            "actual_payment_entry_created_count",
            "actual_payment_entry_cancelled_count",
            "actual_gl_created_count",
            "policy_mutation_performed",
            "actual_policy_mutation_count",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        CLOSEOUT_ITEM_DOCTYPE,
        fields=["name", "closeout", "status", "severity", "category", "check_key", "check_label", "detail", "source_doctype", "source_name"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "closeouts": closeouts,
        "items": items,
        "required_acknowledgement": CLOSEOUT_ACK,
        "guardrails": guardrails(),
        "note": "Phase 10Z closeout summary only. No Payment Entry, GL Entry, Journal Entry, Purchase Invoice, or policy mutation is created.",
    }


def execute_closeout_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("c.status = %(status)s")
        params["status"] = filters.status
    if filters.get("from_date"):
        conditions.append("DATE(c.checked_on) >= %(from_date)s")
        params["from_date"] = filters.from_date
    if filters.get("to_date"):
        conditions.append("DATE(c.checked_on) <= %(to_date)s")
        params["to_date"] = filters.to_date

    data = frappe.db.sql(
        f"""
        SELECT
            c.name AS closeout,
            c.closeout_id,
            c.status,
            c.closeout_status,
            c.closeout_approved,
            c.governed_limited_operation_cycle_closed,
            c.ready_for_governed_steady_state_continuation,
            c.freeze,
            c.rollback,
            c.payment_entry,
            c.payment_entry_status,
            c.payment_entry_docstatus,
            c.invoice_outstanding_restored_amount,
            c.voucher_gl_row_count,
            c.voucher_gl_net_balance,
            c.payment_entry_count_before,
            c.payment_entry_count_after,
            c.payment_entry_gl_count_before,
            c.payment_entry_gl_count_after,
            c.actual_payment_entry_created_count,
            c.actual_payment_entry_cancelled_count,
            c.actual_gl_created_count,
            c.actual_policy_mutation_count,
            c.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Governed Limited Op Closeout` c
        {build_where(conditions)}
        ORDER BY c.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.closeout_id for row in data[:20]],
            "datasets": [
                {"name": "Approved", "values": [int(row.closeout_approved or 0) for row in data[:20]]},
                {"name": "Actual PE Created", "values": [int(row.actual_payment_entry_created_count or 0) for row in data[:20]]},
                {"name": "Actual GL Created", "values": [int(row.actual_gl_created_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Closeouts"), "datatype": "Int"},
        {"value": sum(int(row.closeout_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE Created"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
        {"value": sum(int(row.actual_policy_mutation_count or 0) for row in data), "indicator": "Red", "label": _("Policy Mutations"), "datatype": "Int"},
    ]
    return closeout_columns(), data, None, chart, summary


def closeout_columns():
    return [
        {"fieldname": "closeout", "label": _("Closeout"), "fieldtype": "Link", "options": CLOSEOUT_DOCTYPE, "width": 220},
        {"fieldname": "closeout_id", "label": _("Closeout ID"), "fieldtype": "Data", "width": 390},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 150},
        {"fieldname": "closeout_status", "label": _("Closeout Status"), "fieldtype": "Data", "width": 320},
        {"fieldname": "closeout_approved", "label": _("Approved"), "fieldtype": "Check", "width": 100},
        {"fieldname": "governed_limited_operation_cycle_closed", "label": _("Cycle Closed"), "fieldtype": "Check", "width": 120},
        {"fieldname": "ready_for_governed_steady_state_continuation", "label": _("Steady State Ready"), "fieldtype": "Check", "width": 140},
        {"fieldname": "freeze", "label": _("Freeze"), "fieldtype": "Link", "options": FREEZE_DOCTYPE, "width": 220},
        {"fieldname": "rollback", "label": _("Rollback"), "fieldtype": "Link", "options": "NDIS Governed Limited Op Rollback", "width": 220},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "payment_entry_status", "label": _("PE Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "payment_entry_docstatus", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 110},
        {"fieldname": "invoice_outstanding_restored_amount", "label": _("Restored"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "voucher_gl_row_count", "label": _("Voucher GL Rows"), "fieldtype": "Int", "width": 120},
        {"fieldname": "voucher_gl_net_balance", "label": _("Voucher GL Net"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE Created"), "fieldtype": "Int", "width": 130},
        {"fieldname": "actual_payment_entry_cancelled_count", "label": _("Actual PE Cancelled"), "fieldtype": "Int", "width": 140},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 130},
        {"fieldname": "actual_policy_mutation_count", "label": _("Policy Mutations"), "fieldtype": "Int", "width": 130},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("closeout"):
        conditions.append("i.closeout = %(closeout)s")
        params["closeout"] = filters.closeout
    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.status
    if filters.get("category"):
        conditions.append("i.category = %(category)s")
        params["category"] = filters.category

    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item,
            i.closeout,
            i.status,
            i.severity,
            i.category,
            i.check_key,
            i.check_label,
            i.detail,
            i.source_doctype,
            i.source_name,
            i.checked_on
        FROM `tabNDIS Governed Limited Op Closeout Item` i
        {build_where(conditions)}
        ORDER BY i.creation DESC
        """,
        params,
        as_dict=True,
    )
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": CLOSEOUT_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "closeout", "label": _("Closeout"), "fieldtype": "Link", "options": CLOSEOUT_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 170},
        {"fieldname": "check_key", "label": _("Check Key"), "fieldtype": "Data", "width": 180},
        {"fieldname": "check_label", "label": _("Check Label"), "fieldtype": "Data", "width": 240},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Link", "options": "DocType", "width": 180},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Dynamic Link", "options": "source_doctype", "width": 220},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    status_map = {}
    for row in data:
        status_map[row.status or "Unknown"] = status_map.get(row.status or "Unknown", 0) + 1
    chart = {"data": {"labels": list(status_map), "datasets": [{"name": "Items", "values": list(status_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Items"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Pass"]), "indicator": "Green", "label": _("Pass"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Warning"]), "indicator": "Orange", "label": _("Warnings"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_closeout_report(filters)
    guards = guardrails()
    summary.extend(
        [
            {"value": guards["payment_entry_count"], "indicator": "Blue", "label": _("Current PE Count"), "datatype": "Int"},
            {"value": guards["payment_entry_gl_count"], "indicator": "Blue", "label": _("Current PE GL Count"), "datatype": "Int"},
            {"value": guards["production_batch_enabled_policy_count"], "indicator": "Green", "label": _("Enabled Policies"), "datatype": "Int"},
            {"value": guards["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"},
        ]
    )
    return columns, data, message, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
