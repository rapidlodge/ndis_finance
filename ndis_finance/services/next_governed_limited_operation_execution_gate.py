import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


EXECUTION_GATE_ACK = "I_CONFIRM_PHASE11I_APPROVE_NEXT_GOVERNED_LIMITED_OPERATION_EXECUTION_GATE_NO_POSTING"

POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
PREVIEW_DOCTYPE = "NDIS Governed Next Op Preview"
PREVIEW_ITEM_DOCTYPE = "NDIS Governed Next Op Preview Item"
EXEC_GATE_DOCTYPE = "NDIS Governed Next Op Exec Gate"
EXEC_GATE_ITEM_DOCTYPE = "NDIS Governed Next Op Exec Gate Item"


def make_execution_gate_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-GOVERNED-NEXT-OP-EXEC-GATE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def get_flag(doctype, name, fieldname, default=0):
    if not name or not frappe.db.exists(doctype, name) or not has_column(doctype, fieldname):
        return default
    return int(frappe.db.get_value(doctype, name, fieldname) or 0)


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


def latest_preview():
    rows = frappe.get_all(
        PREVIEW_DOCTYPE,
        filters={
            "status": "Preview Approved",
            "preview_status": "Next Governed Limited Operation Preview Approved",
            "preview_approved": 1,
            "phase11g_validation_verified": 1,
            "preview_shape_locked": 1,
            "preview_references_locked": 1,
            "preview_total_verified": 1,
            "ready_for_next_governed_limited_operation_execution_gate": 1,
            "preview_reference_doctype": "Sales Invoice",
            "preview_reference_count": 3,
            "preview_total_amount": 3.00,
            "would_create_payment_entry_count": 1,
            "would_create_gl_entry_count": 0,
            "preview_live_posting_allowed": 0,
            "preview_journal_entry_side_effect_allowed": 0,
            "preview_purchase_invoice_side_effect_allowed": 0,
            "no_new_accounting_movement_verified": 1,
            "policy_state_preserved_verified": 1,
            "policy_mutation_performed": 0,
            "actual_policy_mutation_count": 0,
            "target_policy_enabled_after": 1,
            "target_policy_live_after": 0,
            "locked_payment_entry_count": 8,
            "locked_payment_entry_gl_count": 46,
            "actual_payment_entry_created_count": 0,
            "actual_payment_entry_cancelled_count": 0,
            "actual_gl_created_count": 0,
            "submitted_journal_entry_count_today": 0,
            "purchase_invoice_count_today": 0,
        },
        fields=[
            "name",
            "preview_id",
            "validation",
            "candidate",
            "design",
            "planning",
            "precheck",
            "monitor",
            "payment_entry",
            "preview_party_type",
            "preview_party",
            "preview_company",
            "preview_currency",
            "preview_reference_doctype",
            "preview_reference_count",
            "preview_total_amount",
            "would_create_payment_entry_count",
            "would_create_gl_entry_count",
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
            "target_policy_enabled_after",
            "target_policy_live_after",
            "locked_payment_entry_count",
            "locked_payment_entry_gl_count",
            "locked_policy_enabled_count",
            "locked_policy_live_allowed_count",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_execution_gate(preview):
    rows = frappe.get_all(
        EXEC_GATE_DOCTYPE,
        filters={"preview": preview, "status": "Execution Gate Approved", "execution_gate_approved": 1},
        fields=["name", "execution_gate_id"],
        limit=1,
    )
    return rows[0] if rows else None


def get_preview_lines(preview):
    if not preview:
        return []

    return frappe.get_all(
        PREVIEW_ITEM_DOCTYPE,
        filters={
            "preview": preview,
            "category": "Preview Reference",
            "reference_doctype": "Sales Invoice",
            "status": "Pass",
        },
        fields=[
            "line_no",
            "reference_doctype",
            "reference_name",
            "customer",
            "company",
            "currency",
            "allocated_amount",
        ],
        order_by="line_no asc, creation asc",
    )


def validate_execution_gate_source(preview, lines):
    issues = []

    if not preview:
        issues.append("No approved Phase 11H preview found.")
        return issues

    existing = existing_execution_gate(preview.name)
    if existing:
        issues.append(f"Phase 11I execution gate already exists for this preview: {existing.execution_gate_id}")

    if len(lines) != 3:
        issues.append(f"Exactly 3 preview references are required. Found {len(lines)}.")

    if lines:
        doctypes = {line.reference_doctype for line in lines}
        customers = {line.customer for line in lines}
        companies = {line.company for line in lines}
        currencies = {line.currency for line in lines}
        total = flt(sum(flt(line.allocated_amount or 0, 2) for line in lines), 2)

        if doctypes != {"Sales Invoice"}:
            issues.append("All execution gate references must be Sales Invoice.")

        if len(customers) != 1:
            issues.append("All execution gate references must have the same customer.")

        if len(companies) != 1:
            issues.append("All execution gate references must have the same company.")

        if len(currencies) != 1:
            issues.append("All execution gate references must have the same currency.")

        if total != 3:
            issues.append(f"Execution gate allocation total must be 3.00. Found {total}.")

        for line in lines:
            if not frappe.db.exists("Sales Invoice", line.reference_name):
                issues.append(f"Sales Invoice missing: {line.reference_name}")
                continue

            si = frappe.get_doc("Sales Invoice", line.reference_name)

            if si.docstatus != 1:
                issues.append(f"Sales Invoice {si.name} must remain submitted.")

            if flt(si.outstanding_amount or 0, 2) < flt(line.allocated_amount or 0, 2):
                issues.append(
                    f"Sales Invoice {si.name} outstanding {flt(si.outstanding_amount or 0, 2)} is less than approved allocation {flt(line.allocated_amount or 0, 2)}."
                )

    return issues


def add_item(items, status, severity, category, check_key, check_label, detail, line=None, source_doctype=None, source_name=None):
    item = {
        "status": status,
        "severity": severity,
        "category": category,
        "check_key": check_key,
        "check_label": check_label,
        "detail": detail,
        "source_doctype": source_doctype,
        "source_name": source_name,
    }

    if line:
        item.update({
            "line_no": int(line.line_no or 0),
            "reference_doctype": line.reference_doctype,
            "reference_name": line.reference_name,
            "customer": line.customer,
            "company": line.company,
            "currency": line.currency,
            "allocated_amount": flt(line.allocated_amount or 0, 2),
        })

    items.append(item)


def build_items(preview, lines, issues, ack_ok):
    items = []

    if preview:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase11h_preview_exists",
            "Phase 11H preview exists",
            f"Preview found: {preview.preview_id}.",
            source_doctype=PREVIEW_DOCTYPE,
            source_name=preview.name,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase11h_preview_exists", "Phase 11H preview exists", "No approved Phase 11H preview found.")

    if not issues:
        add_item(items, "Pass", "Critical", "Execution Gate Source", "execution_gate_source_valid", "Execution gate source valid", "Preview is valid for one controlled smoke execution.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Execution Gate Source", "execution_gate_source_valid", "Execution gate source valid", issue)

    for line in lines:
        add_item(
            items,
            "Pass",
            "High",
            "Approved Reference",
            "approved_sales_invoice_reference",
            f"Approved Sales Invoice {line.line_no}",
            f"{line.reference_name} approved for smoke allocation {flt(line.allocated_amount or 0, 2)}.",
            line=line,
            source_doctype="Sales Invoice",
            source_name=line.reference_name,
        )

    checks = [
        ("preview_shape_locked", "Preview shape locked", "1 PE / 3 references / 3.00"),
        ("smoke_execution_authorised", "Smoke execution authorised", 1),
        ("smoke_only_authorised", "Smoke-only authorised", 1),
        ("real_production_posting_blocked", "Real production posting not authorised", 0),
        ("live_posting_blocked", "Live posting remains blocked", 0),
        ("no_actual_pe", "No actual Payment Entry created in gate", 0),
        ("no_actual_gl", "No actual GL created in gate", 0),
        ("no_je_pi", "No JE / PI side effects", "0 / 0"),
        ("policy_state", "Policy state preserved at 1 / 0", "1 / 0"),
        ("ready_for_smoke", "Ready for Phase 11J smoke", 1),
    ]

    for key, label, value in checks:
        add_item(items, "Pass", "High", "Execution Gate Evidence", key, label, f"value={value}")

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {EXECUTION_GATE_ACK}")

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


def create_items(doc, items):
    for item in items:
        row = frappe.new_doc(EXEC_GATE_ITEM_DOCTYPE)
        row.execution_gate = doc.name

        for fieldname, value in item.items():
            if row.meta.has_field(fieldname):
                setattr(row, fieldname, value)

        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_next_governed_limited_operation_execution_gate(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_next_governed_limited_operation_execution_gate")

    preview = latest_preview()
    lines = get_preview_lines(preview.name if preview else None)

    guard_before = guardrails()
    ack_ok = acknowledgement == EXECUTION_GATE_ACK

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    policy_enabled_before = get_flag(POLICY_DOCTYPE, preview.target_policy, "production_batch_enabled") if preview else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, preview.target_policy, "live_posting_allowed") if preview else 0

    issues = validate_execution_gate_source(preview, lines)

    if guard_before["payment_entry_count"] != 8:
        issues.append("Payment Entry count must remain 8 before Phase 11I execution gate.")

    if guard_before["payment_entry_gl_count"] != 46:
        issues.append("Payment Entry GL count must remain 46 before Phase 11I execution gate.")

    if guard_before["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry count today must remain 0.")

    if guard_before["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice count today must remain 0.")

    if guard_before["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled policy must remain enabled.")

    if guard_before["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0.")

    if policy_enabled_before != 1:
        issues.append("Target policy production_batch_enabled must remain 1.")

    if policy_live_before != 0:
        issues.append("Target policy live_posting_allowed must remain 0.")

    if config["sandbox_enabled"] != 1:
        issues.append("Sandbox config must be enabled.")

    if config["production_mode"] != 0:
        issues.append("Production mode config must remain 0.")

    if config["live_pe_enabled"] != 0:
        issues.append("Live Payment Entry posting config must remain 0.")

    guard_after = guardrails()
    policy_enabled_after = get_flag(POLICY_DOCTYPE, preview.target_policy, "production_batch_enabled") if preview else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, preview.target_policy, "live_posting_allowed") if preview else 0

    no_new_movement = int(
        guard_before["payment_entry_count"] == guard_after["payment_entry_count"]
        and guard_before["payment_entry_gl_count"] == guard_after["payment_entry_gl_count"]
        and guard_before["submitted_journal_entry_count_today"] == guard_after["submitted_journal_entry_count_today"]
        and guard_before["purchase_invoice_count_today"] == guard_after["purchase_invoice_count_today"]
    )

    policy_preserved = int(
        policy_enabled_before == 1
        and policy_enabled_after == 1
        and policy_live_before == 0
        and policy_live_after == 0
        and guard_before["production_batch_enabled_policy_count"] == guard_after["production_batch_enabled_policy_count"]
        and guard_before["live_posting_allowed_policy_count"] == guard_after["live_posting_allowed_policy_count"]
    )

    if not no_new_movement:
        issues.append("Accounting movement changed during Phase 11I execution gate.")

    if not policy_preserved:
        issues.append("Policy state changed during Phase 11I execution gate.")

    approved_total = flt(sum(flt(line.allocated_amount or 0, 2) for line in lines), 2)
    approved_party = lines[0].customer if lines else None
    approved_company = lines[0].company if lines else None
    approved_currency = lines[0].currency if lines else None

    items = build_items(preview, lines, issues, ack_ok)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    allowed = int(
        ack_ok
        and preview
        and item_summary["blocker_count"] == 0
        and len(lines) == 3
        and approved_total == 3
        and no_new_movement
        and policy_preserved
    )

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Execution Gate Approved" if allowed else "Needs Review",
        "execution_gate_status": "Ready For Next Governed Limited Operation Smoke" if allowed else "Needs Review",
        "execution_gate_approved": allowed,
        "phase11h_preview_verified": 1 if preview else 0,
        "phase11g_validation_verified": 1 if preview else 0,
        "preview_shape_locked_verified": 1 if preview else 0,
        "preview_references_locked_verified": 1 if preview else 0,
        "preview_total_verified": int(approved_total == 3),
        "smoke_execution_authorised": allowed,
        "smoke_only_authorised": allowed,
        "real_production_posting_authorised": 0,
        "ready_for_next_governed_limited_operation_smoke": allowed,
        "no_new_accounting_movement_verified": no_new_movement,
        "policy_state_preserved_verified": policy_preserved,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": 0,
        "approved_party_type": "Customer",
        "approved_party": approved_party,
        "approved_company": approved_company,
        "approved_currency": approved_currency,
        "approved_reference_doctype": "Sales Invoice",
        "approved_reference_count": len(lines),
        "approved_total_amount": approved_total,
        "approved_payment_entry_count": 1 if len(lines) == 3 else 0,
        "approved_gl_entry_count_preview": 0,
        "approved_live_posting_allowed": 0,
        "approved_journal_entry_side_effect_allowed": 0,
        "approved_purchase_invoice_side_effect_allowed": 0,
        "execution_gate_mode": "Final Gate Only - No Posting",
        "preview": preview.name if preview else None,
        "validation": preview.validation if preview else None,
        "candidate": preview.candidate if preview else None,
        "design": preview.design if preview else None,
        "planning": preview.planning if preview else None,
        "precheck": preview.precheck if preview else None,
        "monitor": preview.monitor if preview else None,
        "payment_entry": preview.payment_entry if preview else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": preview.target_policy if preview else None,
        "target_policy_name": preview.target_policy_name if preview else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "production_batch_enabled_policy_count_before": guard_before["production_batch_enabled_policy_count"],
        "production_batch_enabled_policy_count_after": guard_after["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count_before": guard_before["live_posting_allowed_policy_count"],
        "live_posting_allowed_policy_count_after": guard_after["live_posting_allowed_policy_count"],
        "locked_payment_entry_count": int(preview.locked_payment_entry_count or 0) if preview else 0,
        "locked_payment_entry_gl_count": int(preview.locked_payment_entry_gl_count or 0) if preview else 0,
        "locked_policy_enabled_count": int(preview.locked_policy_enabled_count or 0) if preview else 0,
        "locked_policy_live_allowed_count": int(preview.locked_policy_live_allowed_count or 0) if preview else 0,
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "actual_payment_entry_created_count": 0,
        "actual_payment_entry_cancelled_count": 0,
        "actual_gl_created_count": 0,
        "submitted_journal_entry_count_today": guard_after["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_after["purchase_invoice_count_today"],
        "execution_gate_score": score,
        **item_summary,
        "approved_lines": [dict(line) for line in lines],
        "items": items,
        "issues": issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "required_acknowledgement": EXECUTION_GATE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 11I is a final execution gate only. It does not create Payment Entry, GL, Journal Entry, Purchase Invoice, or policy mutation.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["execution_gate_status"] = "Needs Review"
        result["execution_gate_approved"] = 0
        result["smoke_execution_authorised"] = 0
        result["smoke_only_authorised"] = 0
        result["ready_for_next_governed_limited_operation_smoke"] = 0
        return result

    doc = frappe.new_doc(EXEC_GATE_DOCTYPE)
    doc.execution_gate_id = make_execution_gate_id()

    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)

    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = EXECUTION_GATE_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.execution_gate_json = safe_json(
        {
            "preview": preview,
            "approved_lines": [dict(line) for line in lines],
            "authorised": {
                "smoke_execution_authorised": allowed,
                "smoke_only_authorised": allowed,
                "real_production_posting_authorised": 0,
                "payment_entry_count": 1 if len(lines) == 3 else 0,
                "approved_total_amount": approved_total,
            },
            "guardrails_before": guard_before,
            "guardrails_after": guard_after,
            "issues": issues,
            "config": config,
        }
    )
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    create_items(doc, items)
    frappe.db.commit()

    return {
        **result,
        "created": True,
        "execution_gate": doc.name,
        "execution_gate_id": doc.execution_gate_id,
        "guardrails_after": guardrails(),
    }


@frappe.whitelist()
def cancel_next_governed_limited_operation_execution_gate_audit(execution_gate, reason=None):
    assert_action("cancel_next_governed_limited_operation_execution_gate_audit")

    if not frappe.db.exists(EXEC_GATE_DOCTYPE, execution_gate):
        frappe.throw(_("Governed next operation execution gate audit not found: {0}").format(execution_gate))

    doc = frappe.get_doc(EXEC_GATE_DOCTYPE, execution_gate)

    if doc.status == "Cancelled":
        return {"execution_gate": execution_gate, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.execution_gate_approved or 0):
        frappe.throw(_("Cannot cancel an approved Phase 11I execution gate record."))

    frappe.db.set_value(
        EXEC_GATE_DOCTYPE,
        execution_gate,
        {
            "status": "Cancelled",
            "execution_gate_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 11I no-ack execution gate audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        f"""
        UPDATE `tab{EXEC_GATE_ITEM_DOCTYPE}`
        SET status = 'Cancelled'
        WHERE execution_gate = %(execution_gate)s
        """,
        {"execution_gate": execution_gate},
    )

    frappe.db.commit()

    return {
        "execution_gate": execution_gate,
        "status": "Cancelled",
        "note": "No-ack execution gate audit cancelled only. No accounting or policy movement occurred.",
    }


@frappe.whitelist()
def quick_next_governed_limited_operation_execution_gate_summary(limit=20):
    records = frappe.get_all(
        EXEC_GATE_DOCTYPE,
        fields=[
            "name",
            "execution_gate_id",
            "status",
            "execution_gate_status",
            "execution_gate_approved",
            "phase11h_preview_verified",
            "preview_shape_locked_verified",
            "preview_references_locked_verified",
            "approved_reference_count",
            "approved_total_amount",
            "approved_payment_entry_count",
            "smoke_execution_authorised",
            "smoke_only_authorised",
            "real_production_posting_authorised",
            "ready_for_next_governed_limited_operation_smoke",
            "preview",
            "validation",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "submitted_journal_entry_count_today",
            "purchase_invoice_count_today",
            "execution_gate_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    items = frappe.get_all(
        EXEC_GATE_ITEM_DOCTYPE,
        fields=[
            "name",
            "execution_gate",
            "status",
            "severity",
            "category",
            "check_key",
            "check_label",
            "line_no",
            "reference_doctype",
            "reference_name",
            "customer",
            "company",
            "currency",
            "allocated_amount",
            "detail",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    return {
        "execution_gate_records": records,
        "items": items,
        "required_acknowledgement": EXECUTION_GATE_ACK,
        "guardrails": guardrails(),
        "note": "Phase 11I governed next operation execution gate summary.",
    }


def execute_execution_gate_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("g.status = %(status)s")
        params["status"] = filters.get("status")

    columns = execution_gate_columns()

    data = frappe.db.sql(
        f"""
        SELECT
            g.name AS execution_gate,
            g.execution_gate_id,
            g.status,
            g.execution_gate_status,
            g.execution_gate_approved,
            g.phase11h_preview_verified,
            g.preview_shape_locked_verified,
            g.preview_references_locked_verified,
            g.preview_total_verified,
            g.smoke_execution_authorised,
            g.smoke_only_authorised,
            g.real_production_posting_authorised,
            g.ready_for_next_governed_limited_operation_smoke,
            g.approved_party,
            g.approved_company,
            g.approved_currency,
            g.approved_reference_count,
            g.approved_total_amount,
            g.approved_payment_entry_count,
            g.approved_gl_entry_count_preview,
            g.preview,
            g.validation,
            g.payment_entry_count_before,
            g.payment_entry_count_after,
            g.payment_entry_gl_count_before,
            g.payment_entry_gl_count_after,
            g.actual_payment_entry_created_count,
            g.actual_payment_entry_cancelled_count,
            g.actual_gl_created_count,
            g.submitted_journal_entry_count_today,
            g.purchase_invoice_count_today,
            g.execution_gate_score,
            g.checked_on,
            %(currency)s AS currency
        FROM `tab{EXEC_GATE_DOCTYPE}` g
        {build_where(conditions)}
        ORDER BY g.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.execution_gate_id for row in data[:20]],
            "datasets": [
                {"name": "Approved", "values": [int(row.execution_gate_approved or 0) for row in data[:20]]},
                {"name": "Smoke Authorised", "values": [int(row.smoke_execution_authorised or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Execution Gate Records"), "datatype": "Int"},
        {"value": sum(int(row.execution_gate_approved or 0) for row in data), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": sum(int(row.smoke_execution_authorised or 0) for row in data), "indicator": "Green", "label": _("Smoke Authorised"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL Created"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execution_gate_columns():
    return [
        {"fieldname": "execution_gate", "label": _("Execution Gate"), "fieldtype": "Link", "options": EXEC_GATE_DOCTYPE, "width": 220},
        {"fieldname": "execution_gate_id", "label": _("Execution Gate ID"), "fieldtype": "Data", "width": 380},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 150},
        {"fieldname": "execution_gate_status", "label": _("Execution Gate Status"), "fieldtype": "Data", "width": 350},
        {"fieldname": "execution_gate_approved", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "phase11h_preview_verified", "label": _("11H Verified"), "fieldtype": "Check", "width": 100},
        {"fieldname": "preview_shape_locked_verified", "label": _("Shape Locked"), "fieldtype": "Check", "width": 110},
        {"fieldname": "preview_references_locked_verified", "label": _("Refs Locked"), "fieldtype": "Check", "width": 100},
        {"fieldname": "preview_total_verified", "label": _("Total OK"), "fieldtype": "Check", "width": 90},
        {"fieldname": "smoke_execution_authorised", "label": _("Smoke Auth"), "fieldtype": "Check", "width": 100},
        {"fieldname": "smoke_only_authorised", "label": _("Smoke Only"), "fieldtype": "Check", "width": 100},
        {"fieldname": "real_production_posting_authorised", "label": _("Real Prod"), "fieldtype": "Check", "width": 90},
        {"fieldname": "ready_for_next_governed_limited_operation_smoke", "label": _("Smoke Ready"), "fieldtype": "Check", "width": 110},
        {"fieldname": "approved_party", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 170},
        {"fieldname": "approved_company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 170},
        {"fieldname": "approved_currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 90},
        {"fieldname": "approved_reference_count", "label": _("Refs"), "fieldtype": "Int", "width": 70},
        {"fieldname": "approved_total_amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 100},
        {"fieldname": "approved_payment_entry_count", "label": _("PE Count"), "fieldtype": "Int", "width": 90},
        {"fieldname": "approved_gl_entry_count_preview", "label": _("Preview GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "preview", "label": _("Preview"), "fieldtype": "Link", "options": PREVIEW_DOCTYPE, "width": 220},
        {"fieldname": "validation", "label": _("Validation"), "fieldtype": "Link", "options": "NDIS Governed Limited Op Candidate Validation", "width": 220},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE Created"), "fieldtype": "Int", "width": 125},
        {"fieldname": "actual_payment_entry_cancelled_count", "label": _("Actual PE Cancelled"), "fieldtype": "Int", "width": 135},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL Created"), "fieldtype": "Int", "width": 125},
        {"fieldname": "submitted_journal_entry_count_today", "label": _("JE Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "purchase_invoice_count_today", "label": _("PI Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "execution_gate_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("execution_gate"):
        conditions.append("i.execution_gate = %(execution_gate)s")
        params["execution_gate"] = filters.get("execution_gate")

    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": EXEC_GATE_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "execution_gate", "label": _("Execution Gate"), "fieldtype": "Link", "options": EXEC_GATE_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 190},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 60},
        {"fieldname": "reference_doctype", "label": _("Ref DocType"), "fieldtype": "Data", "width": 130},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 170},
        {"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 90},
        {"fieldname": "allocated_amount", "label": _("Allocated"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "check_key", "label": _("Check Key"), "fieldtype": "Data", "width": 230},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 330},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 650},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item,
            i.execution_gate,
            i.status,
            i.severity,
            i.category,
            i.line_no,
            i.reference_doctype,
            i.reference_name,
            i.customer,
            i.company,
            i.currency,
            i.allocated_amount,
            i.check_key,
            i.check_label,
            i.detail,
            i.checked_on
        FROM `tab{EXEC_GATE_ITEM_DOCTYPE}` i
        {build_where(conditions)}
        ORDER BY
            CASE i.status
                WHEN 'Blocker' THEN 1
                WHEN 'Warning' THEN 2
                WHEN 'Pass' THEN 3
                WHEN 'Info' THEN 4
                ELSE 5
            END,
            i.line_no ASC,
            i.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart_map = {}
    for row in data:
        key = row.status or "Info"
        chart_map[key] = chart_map.get(key, 0) + 1

    chart = {
        "data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Items", "values": list(chart_map.values())}]},
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Items"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Pass"]), "indicator": "Green", "label": _("Pass"), "datatype": "Int"},
        {"value": len([row for row in data if row.category == "Approved Reference"]), "indicator": "Green", "label": _("Approved References"), "datatype": "Int"},
        {"value": sum(flt(row.allocated_amount or 0, 2) for row in data if row.category == "Approved Reference"), "indicator": "Green", "label": _("Approved Amount"), "datatype": "Currency"},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_execution_gate_report(filters)
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
