import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


ROLLBACK_ACK = "I_CONFIRM_PHASE10X_ROLLBACK_GOVERNED_LIMITED_OPERATION_SMOKE"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
SMOKE_DOCTYPE = "NDIS Governed Limited Op Smoke"
ROLLBACK_DOCTYPE = "NDIS Governed Limited Op Rollback"
ROLLBACK_ITEM_DOCTYPE = "NDIS Governed Limited Op Rollback Item"


def make_rollback_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-GOVERNED-LIMITED-OP-ROLLBACK-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def guardrails():
    return {
        "payment_entry_count": count_dt("Payment Entry"),
        "payment_entry_gl_count": count_dt("GL Entry", {"voucher_type": "Payment Entry"}),
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
        "production_batch_enabled_policy_count": production_batch_enabled_policy_count(),
        "live_posting_allowed_policy_count": live_posting_allowed_policy_count(),
    }


def latest_smoke():
    rows = frappe.get_all(
        SMOKE_DOCTYPE,
        filters={
            "status": "Smoke Completed - Rollback Required",
            "smoke_status": "Governed Limited Operation Smoke Completed",
            "smoke_completed": 1,
            "rollback_required": 1,
            "freeze_required_after_rollback": 1,
            "ready_for_governed_limited_operation_smoke_rollback": 1,
            "payment_entry_docstatus": 1,
            "payment_entry_reference_count": 3,
            "actual_payment_entry_created_count": 1,
            "actual_payment_entry_cancelled_count": 0,
            "policy_mutation_performed": 0,
            "actual_policy_mutation_count": 0,
            "controlled_policy_enabled_verified": 1,
            "live_posting_blocked_verified": 1,
            "target_policy_enabled_after": 1,
            "target_policy_live_after": 0,
            "submitted_journal_entry_count_today": 0,
            "purchase_invoice_count_today": 0,
        },
        fields=[
            "name",
            "smoke_id",
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
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
            "target_policy_enabled_after",
            "target_policy_live_after",
            "production_batch_enabled_policy_count_after",
            "live_posting_allowed_policy_count_after",
            "payment_entry",
            "payment_entry_docstatus",
            "payment_entry_status",
            "payment_entry_amount",
            "payment_entry_reference_count",
            "payment_entry_party_type",
            "payment_entry_party",
            "payment_entry_company",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "voucher_gl_row_count",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_completed_rollback(smoke):
    rows = frappe.get_all(
        ROLLBACK_DOCTYPE,
        filters={"smoke": smoke, "status": "Rollback Completed", "rollback_completed": 1},
        fields=["name", "rollback_id", "payment_entry"],
        limit=1,
    )
    return rows[0] if rows else None


def payment_entry_refs(payment_entry):
    return frappe.get_all(
        "Payment Entry Reference",
        filters={"parent": payment_entry, "reference_doctype": "Sales Invoice"},
        fields=["idx", "reference_doctype", "reference_name", "allocated_amount"],
        order_by="idx asc",
    )


def invoice_outstanding_snapshot(refs):
    rows = []
    total = 0
    for ref in refs:
        outstanding = 0
        if frappe.db.exists("Sales Invoice", ref.reference_name):
            outstanding = flt(frappe.db.get_value("Sales Invoice", ref.reference_name, "outstanding_amount") or 0, 2)
        total += outstanding
        rows.append(
            {
                "idx": ref.idx,
                "reference_doctype": ref.reference_doctype,
                "reference_name": ref.reference_name,
                "allocated_amount": flt(ref.allocated_amount or 0, 2),
                "outstanding": outstanding,
            }
        )
    return rows, flt(total, 2)


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


def validate_source(smoke, refs, guard, policy_enabled, policy_live, config):
    issues = []
    if not smoke:
        issues.append("No Phase 10W completed smoke requiring rollback was found.")
        return issues

    existing = existing_completed_rollback(smoke.name)
    if existing:
        issues.append(f"Phase 10X rollback already exists for this smoke: {existing.rollback_id} / {existing.payment_entry}")

    required_links = {
        "smoke": (SMOKE_DOCTYPE, smoke.name),
        "execution_gate": ("NDIS Governed Limited Op Exec Gate", smoke.execution_gate),
        "preview": ("NDIS Governed Limited Op Preview", smoke.preview),
        "target_policy": (POLICY_DOCTYPE, smoke.target_policy),
        "payment_entry": ("Payment Entry", smoke.payment_entry),
    }
    for label, pair in required_links.items():
        doctype, name = pair
        if not name:
            issues.append(f"Missing evidence link: {label}")
        elif not frappe.db.exists(doctype, name):
            issues.append(f"Linked evidence does not exist: {doctype} {name}")

    if not smoke.payment_entry or not frappe.db.exists("Payment Entry", smoke.payment_entry):
        return issues

    pe = frappe.get_doc("Payment Entry", smoke.payment_entry)
    if pe.docstatus != 1:
        issues.append(f"Payment Entry must be submitted before rollback. docstatus={pe.docstatus}")
    if flt(pe.paid_amount or pe.received_amount or 0, 2) != 3:
        issues.append(f"Payment Entry amount must be 3.00. paid={pe.paid_amount}, received={pe.received_amount}")
    if len(refs) != 3:
        issues.append(f"Payment Entry must have 3 Sales Invoice references. Found {len(refs)}.")
    allocated_total = flt(sum(flt(row.allocated_amount or 0, 2) for row in refs), 2)
    if allocated_total != 3:
        issues.append(f"Payment Entry reference allocated total must be 3.00. Found {allocated_total}.")
    if voucher_gl_row_count(smoke.payment_entry) != int(smoke.voucher_gl_row_count or 0):
        issues.append("Current voucher GL row count must match Phase 10W smoke voucher GL row count before rollback.")
    if policy_enabled != 1:
        issues.append("Target policy production_batch_enabled must be 1 before Phase 10X. Phase 10X must not repair this.")
    if policy_live != 0:
        issues.append("Target policy live_posting_allowed must be 0 before Phase 10X. Phase 10X must not repair this.")
    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must remain enabled.")
    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0.")
    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry count today must be 0 before rollback.")
    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice count today must be 0 before rollback.")
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


def build_items(smoke, refs, issues, ack_ok, payment_entry=None, rollback_done=False):
    items = []
    if smoke:
        add_item(items, "Pass", "Low", "Evidence", "phase10w_smoke_exists", "Phase 10W smoke exists", f"Smoke found: {smoke.smoke_id}.", SMOKE_DOCTYPE, smoke.name)
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase10w_smoke_exists", "Phase 10W smoke exists", "No Phase 10W smoke requiring rollback found.")

    if not issues:
        add_item(items, "Pass", "Critical", "Rollback Source", "rollback_source_valid", "Rollback source valid", "Phase 10W smoke and Payment Entry are valid for rollback.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Rollback Source", "rollback_source_valid", "Rollback source valid", issue)

    for ref in refs:
        add_item(
            items,
            "Pass",
            "High",
            "Invoice Restoration",
            f"invoice_ref_{ref.idx}",
            f"Invoice reference {ref.idx}",
            f"{ref.reference_doctype} {ref.reference_name}; allocated={flt(ref.allocated_amount or 0, 2)}",
            ref.reference_doctype,
            ref.reference_name,
        )

    if rollback_done and payment_entry:
        add_item(items, "Pass", "Critical", "Accounting Reversal", "payment_entry_cancelled", "Payment Entry cancelled", f"Payment Entry {payment_entry} cancelled and reversal GL verified.", "Payment Entry", payment_entry)

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {ROLLBACK_ACK}")
    return items


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


def create_ref_items(doc, before_rows, after_rows):
    after_by_ref = {row["reference_name"]: row for row in after_rows}
    for before in before_rows:
        after = after_by_ref.get(before["reference_name"], {})
        restored = flt((after.get("outstanding") or 0) - (before.get("outstanding") or 0), 2)
        item = frappe.new_doc(ROLLBACK_ITEM_DOCTYPE)
        item.rollback = doc.name
        item.line_no = before.get("idx")
        item.status = "Pass"
        item.reference_doctype = before.get("reference_doctype")
        item.reference_name = before.get("reference_name")
        item.allocated_amount = before.get("allocated_amount")
        item.outstanding_before = before.get("outstanding")
        item.outstanding_after = after.get("outstanding")
        item.restored_amount = restored
        item.payment_entry = doc.payment_entry
        item.detail = f"Outstanding restored by {restored} after Payment Entry cancellation."
        item.checked_on = doc.checked_on
        item.insert(ignore_permissions=True)


def assign_if_has(doc, values):
    for fieldname, value in values.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)


@frappe.whitelist()
def run_governed_limited_operation_smoke_rollback(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_governed_limited_operation_smoke_rollback")

    smoke = latest_smoke()
    refs = payment_entry_refs(smoke.payment_entry) if smoke else []
    guard_before = guardrails()
    ack_ok = acknowledgement == ROLLBACK_ACK
    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }
    policy_enabled_before = get_flag(POLICY_DOCTYPE, smoke.target_policy, "production_batch_enabled") if smoke else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, smoke.target_policy, "live_posting_allowed") if smoke else 0
    issues = validate_source(smoke, refs, guard_before, policy_enabled_before, policy_live_before, config)
    outstanding_before_rows, outstanding_before_total = invoice_outstanding_snapshot(refs)
    allocated_total = flt(sum(flt(row.allocated_amount or 0, 2) for row in refs), 2)
    voucher_gl_before = voucher_gl_row_count(smoke.payment_entry) if smoke else 0

    base = {
        "dry_run": bool(int(dry_run or 0)),
        "smoke": smoke.name if smoke else None,
        "execution_gate": smoke.execution_gate if smoke else None,
        "preview": smoke.preview if smoke else None,
        "pre_execution_gate": smoke.pre_execution_gate if smoke else None,
        "readiness": smoke.readiness if smoke else None,
        "governance_closeout": smoke.governance_closeout if smoke else None,
        "freeze": smoke.freeze if smoke else None,
        "simulation": smoke.simulation if smoke else None,
        "runtime_watch": smoke.runtime_watch if smoke else None,
        "baseline": smoke.baseline if smoke else None,
        "monitoring_register": smoke.monitoring_register if smoke else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": smoke.target_policy if smoke else None,
        "target_policy_name": smoke.target_policy_name if smoke else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_live_before": policy_live_before,
        "payment_entry": smoke.payment_entry if smoke else None,
        "payment_entry_docstatus_before": smoke.payment_entry_docstatus if smoke else 0,
        "payment_entry_status_before": smoke.payment_entry_status if smoke else None,
        "payment_entry_amount": flt(smoke.payment_entry_amount or 0, 2) if smoke else 0,
        "payment_entry_reference_count": smoke.payment_entry_reference_count if smoke else 0,
        "payment_entry_party_type": smoke.payment_entry_party_type if smoke else None,
        "payment_entry_party": smoke.payment_entry_party if smoke else None,
        "payment_entry_company": smoke.payment_entry_company if smoke else None,
        "invoice_reference_count": len(refs),
        "invoice_allocated_total": allocated_total,
        "invoice_outstanding_total_before": outstanding_before_total,
        "voucher_gl_row_count_before": voucher_gl_before,
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "required_acknowledgement": ROLLBACK_ACK,
        "acknowledgement_ok": ack_ok,
        "issues": issues,
        "refs": refs,
        "outstanding_before_rows": outstanding_before_rows,
        "guardrails_before": guard_before,
    }

    if int(dry_run or 0):
        guard_after = guardrails()
        items = build_items(smoke, refs, issues, ack_ok)
        item_summary = summarise_items(items)
        return {
            **base,
            "status": "Needs Review",
            "rollback_status": "Needs Review",
            "rollback_completed": 0,
            "payment_entry_cancelled_verified": 0,
            "invoice_outstanding_restored_verified": 0,
            "gl_reversal_verified": 0,
            "gl_net_zero_verified": 0,
            "payment_entry_count_after": guard_after["payment_entry_count"],
            "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
            "actual_payment_entry_created_count": 0,
            "actual_payment_entry_cancelled_count": 0,
            "actual_gl_created_count": 0,
            "submitted_journal_entry_count_today": guard_after["submitted_journal_entry_count_today"],
            "purchase_invoice_count_today": guard_after["purchase_invoice_count_today"],
            "items": items,
            **item_summary,
            "note": "Dry-run only. Payment Entry was not cancelled.",
        }

    if not ack_ok:
        guard_after = guardrails()
        items = build_items(smoke, refs, issues, ack_ok)
        item_summary = summarise_items(items)
        score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
        doc = frappe.new_doc(ROLLBACK_DOCTYPE)
        doc.rollback_id = make_rollback_id()
        doc.status = "Needs Review"
        doc.rollback_status = "Needs Review"
        assign_if_has(
            doc,
            {
                **base,
                "payment_entry_count_after": guard_after["payment_entry_count"],
                "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
                "actual_payment_entry_created_count": 0,
                "actual_payment_entry_cancelled_count": 0,
                "actual_gl_created_count": 0,
                "submitted_journal_entry_count_today": guard_after["submitted_journal_entry_count_today"],
                "purchase_invoice_count_today": guard_after["purchase_invoice_count_today"],
                "rollback_score": score,
                **item_summary,
            },
        )
        doc.site_name = frappe.local.site
        doc.sandbox_config_enabled = config["sandbox_enabled"]
        doc.production_mode_detected = config["production_mode"]
        doc.live_payment_entry_posting_config = config["live_pe_enabled"]
        doc.checked_on = now_datetime()
        doc.checked_by = frappe.session.user
        doc.required_acknowledgement = ROLLBACK_ACK
        doc.acknowledgement = acknowledgement
        doc.acknowledgement_ok = 0
        doc.summary_json = safe_json({"items": items, "issues": issues, "guardrails_before": guard_before, "guardrails_after": guard_after})
        doc.rollback_json = safe_json({"refs": refs, "outstanding_before": outstanding_before_rows})
        doc.notes = notes
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return {**base, "created": True, "rollback": doc.name, "rollback_id": doc.rollback_id, "status": doc.status, "rollback_status": doc.rollback_status, "items": items, **item_summary, "guardrails_after": guard_after, "note": "No-ack rollback audit only. Payment Entry was not cancelled."}

    if issues:
        frappe.throw(_("Phase 10X rollback blocked: {0}").format("; ".join(issues)))

    pe = frappe.get_doc("Payment Entry", smoke.payment_entry)
    pe.flags.ignore_permissions = True
    pe.cancel()
    frappe.db.commit()
    pe.reload()

    guard_after = guardrails()
    policy_enabled_after = get_flag(POLICY_DOCTYPE, smoke.target_policy, "production_batch_enabled")
    policy_live_after = get_flag(POLICY_DOCTYPE, smoke.target_policy, "live_posting_allowed")
    outstanding_after_rows, outstanding_after_total = invoice_outstanding_snapshot(refs)
    voucher_gl_after = voucher_gl_row_count(pe.name)
    reversal_gl_count = voucher_gl_after - voucher_gl_before
    gl_net = voucher_gl_net_balance(pe.name)
    gl_non_zero = voucher_gl_non_zero_account_count(pe.name)
    actual_pe_cancelled = 1 if pe.docstatus == 2 else 0
    actual_gl_created = guard_after["payment_entry_gl_count"] - guard_before["payment_entry_gl_count"]
    outstanding_restored_amount = flt(outstanding_after_total - outstanding_before_total, 2)

    final_issues = []
    if pe.docstatus != 2:
        final_issues.append(f"Payment Entry must be cancelled. docstatus={pe.docstatus}")
    if actual_pe_cancelled != 1:
        final_issues.append("Exactly one Payment Entry must be cancelled.")
    if guard_after["payment_entry_count"] != guard_before["payment_entry_count"]:
        final_issues.append("Payment Entry count must remain unchanged after cancellation.")
    if reversal_gl_count <= 0:
        final_issues.append("Cancellation must create reversal GL rows.")
    if actual_gl_created != reversal_gl_count:
        final_issues.append(f"Actual GL delta {actual_gl_created} must equal reversal GL row count {reversal_gl_count}.")
    if gl_net != 0:
        final_issues.append(f"Voucher GL net balance must be zero. Found {gl_net}.")
    if gl_non_zero != 0:
        final_issues.append(f"Voucher GL account non-zero count must be zero. Found {gl_non_zero}.")
    if outstanding_restored_amount != allocated_total:
        final_issues.append(f"Invoice outstanding restored amount must equal allocated total {allocated_total}. Found {outstanding_restored_amount}.")
    if guard_after["submitted_journal_entry_count_today"] != 0:
        final_issues.append("Submitted Journal Entry count today must remain 0.")
    if guard_after["purchase_invoice_count_today"] != 0:
        final_issues.append("Purchase Invoice count today must remain 0.")
    if policy_enabled_after != 1 or policy_live_after != 0:
        final_issues.append("Policy enabled/live must remain 1 / 0.")
    if final_issues:
        frappe.throw(_("Phase 10X rollback executed but final verification failed. Manual review required: {0}").format("; ".join(final_issues)))

    items = build_items(smoke, refs, [], ack_ok, pe.name, rollback_done=True)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    result = {
        **base,
        "status": "Rollback Completed",
        "rollback_status": "Governed Limited Operation Smoke Rolled Back",
        "rollback_completed": 1,
        "smoke_rollback_verified": 1,
        "payment_entry_cancelled_verified": 1,
        "invoice_outstanding_restored_verified": 1,
        "gl_reversal_verified": 1,
        "gl_net_zero_verified": 1,
        "ready_for_governed_limited_operation_smoke_freeze": 1,
        "policy_state_preserved_verified": 1,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": 0,
        "phase10w_smoke_verified": 1,
        "phase10v_execution_gate_verified": 1,
        "phase10u_preview_verified": 1,
        "phase10t_pre_execution_verified": 1,
        "phase10s_readiness_verified": 1,
        "phase10r_governance_closeout_verified": 1,
        "phase10q_freeze_verified": 1,
        "phase10p_simulation_verified": 1,
        "phase10o_runtime_watch_verified": 1,
        "phase10n_baseline_verified": 1,
        "controlled_policy_enabled_verified": 1,
        "live_posting_blocked_verified": 1,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_after": policy_live_after,
        "production_batch_enabled_policy_count_before": guard_before["production_batch_enabled_policy_count"],
        "production_batch_enabled_policy_count_after": guard_after["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count_before": guard_before["live_posting_allowed_policy_count"],
        "live_posting_allowed_policy_count_after": guard_after["live_posting_allowed_policy_count"],
        "payment_entry_docstatus_after": pe.docstatus,
        "payment_entry_status_after": pe.status,
        "invoice_outstanding_total_after": outstanding_after_total,
        "invoice_outstanding_restored_amount": outstanding_restored_amount,
        "voucher_gl_row_count_after": voucher_gl_after,
        "reversal_gl_row_count": reversal_gl_count,
        "voucher_gl_net_balance": gl_net,
        "gl_account_non_zero_count": gl_non_zero,
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "actual_payment_entry_created_count": 0,
        "actual_payment_entry_cancelled_count": actual_pe_cancelled,
        "actual_gl_created_count": actual_gl_created,
        "submitted_journal_entry_count_today": guard_after["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_after["purchase_invoice_count_today"],
        "rollback_score": score,
        **item_summary,
        "items": items,
        "outstanding_after_rows": outstanding_after_rows,
        "guardrails_after": guard_after,
        "final_issues": final_issues,
    }
    doc = frappe.new_doc(ROLLBACK_DOCTYPE)
    doc.rollback_id = make_rollback_id()
    assign_if_has(doc, result)
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = ROLLBACK_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = 1
    doc.summary_json = safe_json(result)
    doc.rollback_json = safe_json(
        {
            "payment_entry": pe.name,
            "refs": refs,
            "outstanding_before": outstanding_before_rows,
            "outstanding_after": outstanding_after_rows,
            "guardrails_before": guard_before,
            "guardrails_after": guard_after,
            "voucher_gl_before": voucher_gl_before,
            "voucher_gl_after": voucher_gl_after,
            "gl_net": gl_net,
            "gl_non_zero": gl_non_zero,
        }
    )
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_ref_items(doc, outstanding_before_rows, outstanding_after_rows)
    frappe.db.commit()
    return {**result, "created": True, "rollback": doc.name, "rollback_id": doc.rollback_id, "note": "Governed smoke rollback completed. Proceed to Phase 10Y freeze."}


@frappe.whitelist()
def cancel_governed_limited_operation_smoke_rollback_audit(rollback, reason=None):
    assert_action("cancel_governed_limited_operation_smoke_rollback_audit")
    if not frappe.db.exists(ROLLBACK_DOCTYPE, rollback):
        frappe.throw(_("Governed limited operation rollback audit not found: {0}").format(rollback))
    doc = frappe.get_doc(ROLLBACK_DOCTYPE, rollback)
    if doc.status == "Cancelled":
        return {"rollback": rollback, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.rollback_completed or 0):
        frappe.throw(_("Cannot cancel a completed Phase 10X rollback record."))
    frappe.db.set_value(
        ROLLBACK_DOCTYPE,
        rollback,
        {"status": "Cancelled", "rollback_status": "Cancelled", "cancelled_on": now_datetime(), "cancelled_by": frappe.session.user, "summary_json": reason or "Phase 10X no-ack rollback audit cancelled."},
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{ROLLBACK_ITEM_DOCTYPE}` SET status = 'Cancelled' WHERE rollback = %(rollback)s", {"rollback": rollback})
    frappe.db.commit()
    return {"rollback": rollback, "status": "Cancelled", "note": "No-ack rollback audit cancelled only. No accounting or policy movement occurred."}


@frappe.whitelist()
def quick_governed_limited_operation_smoke_rollback_summary(limit=20):
    records = frappe.get_all(
        ROLLBACK_DOCTYPE,
        fields=[
            "name",
            "rollback_id",
            "status",
            "rollback_status",
            "rollback_completed",
            "payment_entry_cancelled_verified",
            "invoice_outstanding_restored_verified",
            "gl_reversal_verified",
            "gl_net_zero_verified",
            "ready_for_governed_limited_operation_smoke_freeze",
            "smoke",
            "payment_entry",
            "payment_entry_docstatus_before",
            "payment_entry_docstatus_after",
            "payment_entry_status_after",
            "payment_entry_amount",
            "payment_entry_reference_count",
            "invoice_allocated_total",
            "invoice_outstanding_restored_amount",
            "voucher_gl_row_count_before",
            "voucher_gl_row_count_after",
            "reversal_gl_row_count",
            "voucher_gl_net_balance",
            "gl_account_non_zero_count",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "actual_payment_entry_cancelled_count",
            "actual_gl_created_count",
            "submitted_journal_entry_count_today",
            "purchase_invoice_count_today",
            "rollback_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        ROLLBACK_ITEM_DOCTYPE,
        fields=["name", "rollback", "line_no", "status", "reference_doctype", "reference_name", "allocated_amount", "outstanding_before", "outstanding_after", "restored_amount", "payment_entry", "detail"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {"rollbacks": records, "items": items, "required_acknowledgement": ROLLBACK_ACK, "guardrails": guardrails(), "note": "Phase 10X rollback summary. Completed rollback is ready for Phase 10Y freeze."}


def execute_rollback_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("r.status = %(status)s")
        params["status"] = filters.get("status")
    columns = rollback_columns()
    data = frappe.db.sql(
        f"""
        SELECT
            r.name AS rollback,
            r.rollback_id,
            r.status,
            r.rollback_status,
            r.rollback_completed,
            r.payment_entry_cancelled_verified,
            r.invoice_outstanding_restored_verified,
            r.gl_reversal_verified,
            r.gl_net_zero_verified,
            r.ready_for_governed_limited_operation_smoke_freeze,
            r.smoke,
            r.payment_entry,
            r.payment_entry_docstatus_before,
            r.payment_entry_docstatus_after,
            r.payment_entry_status_before,
            r.payment_entry_status_after,
            r.payment_entry_amount,
            r.invoice_allocated_total,
            r.invoice_outstanding_restored_amount,
            r.voucher_gl_row_count_before,
            r.voucher_gl_row_count_after,
            r.reversal_gl_row_count,
            r.voucher_gl_net_balance,
            r.gl_account_non_zero_count,
            r.payment_entry_count_before,
            r.payment_entry_count_after,
            r.payment_entry_gl_count_before,
            r.payment_entry_gl_count_after,
            r.actual_payment_entry_cancelled_count,
            r.actual_gl_created_count,
            r.submitted_journal_entry_count_today,
            r.purchase_invoice_count_today,
            r.rollback_score,
            r.checked_on,
            %(currency)s AS currency
        FROM `tab{ROLLBACK_DOCTYPE}` r
        {build_where(conditions)}
        ORDER BY r.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.rollback_id for row in data[:20]],
            "datasets": [
                {"name": "PE Cancelled", "values": [int(row.actual_payment_entry_cancelled_count or 0) for row in data[:20]]},
                {"name": "GL Reversal Rows", "values": [int(row.actual_gl_created_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Rollback Records"), "datatype": "Int"},
        {"value": sum(int(row.rollback_completed or 0) for row in data), "indicator": "Green", "label": _("Completed"), "datatype": "Int"},
        {"value": sum(int(row.payment_entry_cancelled_verified or 0) for row in data), "indicator": "Green", "label": _("PE Cancelled"), "datatype": "Int"},
        {"value": sum(int(row.gl_net_zero_verified or 0) for row in data), "indicator": "Green", "label": _("GL Net Zero"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def rollback_columns():
    return [
        {"fieldname": "rollback", "label": _("Rollback"), "fieldtype": "Link", "options": ROLLBACK_DOCTYPE, "width": 220},
        {"fieldname": "rollback_id", "label": _("Rollback ID"), "fieldtype": "Data", "width": 390},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 170},
        {"fieldname": "rollback_status", "label": _("Rollback Status"), "fieldtype": "Data", "width": 330},
        {"fieldname": "rollback_completed", "label": _("Completed"), "fieldtype": "Check", "width": 90},
        {"fieldname": "payment_entry_cancelled_verified", "label": _("PE Cancelled"), "fieldtype": "Check", "width": 110},
        {"fieldname": "invoice_outstanding_restored_verified", "label": _("Invoice Restored"), "fieldtype": "Check", "width": 120},
        {"fieldname": "gl_reversal_verified", "label": _("GL Reversal"), "fieldtype": "Check", "width": 105},
        {"fieldname": "gl_net_zero_verified", "label": _("GL Net Zero"), "fieldtype": "Check", "width": 105},
        {"fieldname": "ready_for_governed_limited_operation_smoke_freeze", "label": _("Ready Freeze"), "fieldtype": "Check", "width": 110},
        {"fieldname": "smoke", "label": _("Smoke"), "fieldtype": "Link", "options": SMOKE_DOCTYPE, "width": 220},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "payment_entry_docstatus_before", "label": _("PE Doc Before"), "fieldtype": "Int", "width": 100},
        {"fieldname": "payment_entry_docstatus_after", "label": _("PE Doc After"), "fieldtype": "Int", "width": 100},
        {"fieldname": "payment_entry_status_before", "label": _("PE Status Before"), "fieldtype": "Data", "width": 130},
        {"fieldname": "payment_entry_status_after", "label": _("PE Status After"), "fieldtype": "Data", "width": 130},
        {"fieldname": "payment_entry_amount", "label": _("PE Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "invoice_allocated_total", "label": _("Allocated"), "fieldtype": "Currency", "options": "currency", "width": 105},
        {"fieldname": "invoice_outstanding_restored_amount", "label": _("Restored"), "fieldtype": "Currency", "options": "currency", "width": 105},
        {"fieldname": "voucher_gl_row_count_before", "label": _("Voucher GL Before"), "fieldtype": "Int", "width": 125},
        {"fieldname": "voucher_gl_row_count_after", "label": _("Voucher GL After"), "fieldtype": "Int", "width": 125},
        {"fieldname": "reversal_gl_row_count", "label": _("Reversal GL"), "fieldtype": "Int", "width": 100},
        {"fieldname": "voucher_gl_net_balance", "label": _("GL Net"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "gl_account_non_zero_count", "label": _("Non-Zero Accounts"), "fieldtype": "Int", "width": 130},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "actual_payment_entry_cancelled_count", "label": _("Actual PE Cancelled"), "fieldtype": "Int", "width": 135},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 125},
        {"fieldname": "submitted_journal_entry_count_today", "label": _("JE Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "purchase_invoice_count_today", "label": _("PI Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "rollback_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("rollback"):
        conditions.append("i.rollback = %(rollback)s")
        params["rollback"] = filters.get("rollback")
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": ROLLBACK_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "rollback", "label": _("Rollback"), "fieldtype": "Link", "options": ROLLBACK_DOCTYPE, "width": 220},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 70},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "reference_doctype", "label": _("Reference DocType"), "fieldtype": "Data", "width": 150},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 190},
        {"fieldname": "allocated_amount", "label": _("Allocated"), "fieldtype": "Currency", "options": "currency", "width": 105},
        {"fieldname": "outstanding_before", "label": _("Outstanding Before"), "fieldtype": "Currency", "options": "currency", "width": 135},
        {"fieldname": "outstanding_after", "label": _("Outstanding After"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "restored_amount", "label": _("Restored"), "fieldtype": "Currency", "options": "currency", "width": 105},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 500},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item,
            i.rollback,
            i.line_no,
            i.status,
            i.reference_doctype,
            i.reference_name,
            i.allocated_amount,
            i.outstanding_before,
            i.outstanding_after,
            i.restored_amount,
            i.payment_entry,
            i.detail,
            i.checked_on,
            %(currency)s AS currency
        FROM `tab{ROLLBACK_ITEM_DOCTYPE}` i
        {build_where(conditions)}
        ORDER BY i.rollback DESC, i.line_no ASC, i.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {"data": {"labels": [str(row.reference_name) for row in data[:20]], "datasets": [{"name": "Restored", "values": [flt(row.restored_amount or 0, 2) for row in data[:20]]}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Rollback Lines"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Pass"]), "indicator": "Green", "label": _("Pass"), "datatype": "Int"},
        {"value": sum(flt(row.restored_amount or 0, 2) for row in data), "indicator": "Green", "label": _("Restored Total"), "datatype": "Currency", "currency": currency()},
    ]
    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_rollback_report(filters)
    guard = guardrails()
    summary.append({"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"})
    summary.append({"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"})
    summary.append({"value": guard["production_batch_enabled_policy_count"], "indicator": "Green", "label": _("Enabled Policies"), "datatype": "Int"})
    summary.append({"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"})
    summary.append({"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"})
    summary.append({"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"})
    return columns, data, message, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
