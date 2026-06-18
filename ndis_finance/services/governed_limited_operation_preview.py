import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


PREVIEW_ACK = "I_CONFIRM_PHASE10U_PREVIEW_ONE_GOVERNED_LIMITED_OPERATION_NO_POSTING"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
GATE_DOCTYPE = "NDIS Governed Limited Op Pre Exec"
PREVIEW_DOCTYPE = "NDIS Governed Limited Op Preview"
PREVIEW_ITEM_DOCTYPE = "NDIS Governed Limited Op Preview Item"


def make_preview_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-GOVERNED-LIMITED-OP-PREVIEW-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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
    return count_dt(POLICY_DOCTYPE, {"production_batch_enabled": 1}) if has_column(POLICY_DOCTYPE, "production_batch_enabled") else 0


def live_posting_allowed_policy_count():
    return count_dt(POLICY_DOCTYPE, {"live_posting_allowed": 1}) if has_column(POLICY_DOCTYPE, "live_posting_allowed") else 0


def guardrails():
    return {
        "payment_entry_count": count_dt("Payment Entry"),
        "payment_entry_gl_count": count_dt("GL Entry", {"voucher_type": "Payment Entry"}),
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
        "production_batch_enabled_policy_count": production_batch_enabled_policy_count(),
        "live_posting_allowed_policy_count": live_posting_allowed_policy_count(),
    }


def latest_pre_execution_gate():
    rows = frappe.get_all(
        GATE_DOCTYPE,
        filters={
            "status": "Pre-Execution Approved",
            "pre_execution_status": "Ready For One Governed Limited Operation",
            "pre_execution_approved": 1,
            "ready_for_one_governed_limited_operation": 1,
            "ready_for_governed_limited_operation_preview": 1,
            "operation_shape_validated": 1,
            "operation_shape_locked": 1,
            "readiness_verified": 1,
            "locked_runtime_limits_verified": 1,
            "live_posting_remains_blocked": 1,
            "journal_entry_side_effect_remains_blocked": 1,
            "purchase_invoice_side_effect_remains_blocked": 1,
            "pre_execution_only_verified": 1,
            "no_new_accounting_movement_verified": 1,
            "policy_state_preserved_verified": 1,
            "policy_mutation_performed": 0,
            "actual_policy_mutation_count": 0,
            "phase10s_readiness_verified": 1,
            "phase10r_governance_closeout_verified": 1,
            "phase10q_freeze_verified": 1,
            "phase10p_simulation_verified": 1,
            "phase10o_runtime_watch_verified": 1,
            "phase10n_baseline_verified": 1,
            "controlled_policy_enabled_verified": 1,
            "live_posting_blocked_verified": 1,
            "target_policy_enabled_after": 1,
            "target_policy_live_after": 0,
            "requested_batch_line_count": 3,
            "requested_payment_entry_count": 1,
            "requested_live_posting": 0,
            "requested_journal_entry_side_effect": 0,
            "requested_purchase_invoice_side_effect": 0,
            "actual_payment_entry_created_count": 0,
            "actual_payment_entry_cancelled_count": 0,
            "actual_gl_created_count": 0,
            "submitted_journal_entry_count_today": 0,
            "purchase_invoice_count_today": 0,
        },
        fields=[
            "name",
            "pre_execution_id",
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
            "requested_batch_line_count",
            "requested_batch_amount",
            "requested_payment_entry_count",
            "requested_live_posting",
            "requested_journal_entry_side_effect",
            "requested_purchase_invoice_side_effect",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def existing_preview(pre_execution_gate):
    if not pre_execution_gate:
        return None
    rows = frappe.get_all(
        PREVIEW_DOCTYPE,
        filters={"pre_execution_gate": pre_execution_gate, "status": "Previewed", "preview_completed": 1},
        fields=["name", "preview_id"],
        limit=1,
    )
    return rows[0] if rows else None


def candidate_payment_entry():
    rows = frappe.db.sql(
        """
        SELECT pe.name, pe.party, pe.party_type, pe.company,
               pe.paid_amount, pe.received_amount, pe.posting_date,
               COUNT(per.name) AS ref_count,
               ROUND(SUM(per.allocated_amount), 2) AS allocated_total
        FROM `tabPayment Entry` pe
        INNER JOIN `tabPayment Entry Reference` per ON per.parent = pe.name
        WHERE pe.docstatus = 2
          AND per.reference_doctype = 'Sales Invoice'
          AND per.allocated_amount > 0
        GROUP BY pe.name, pe.party, pe.party_type, pe.company, pe.paid_amount, pe.received_amount, pe.posting_date
        HAVING ref_count = 3 AND allocated_total = 3
        ORDER BY pe.modified DESC, pe.creation DESC
        LIMIT 1
        """,
        as_dict=True,
    )
    return rows[0] if rows else None


def build_preview_lines_from_payment_entry(pe_name):
    refs = frappe.get_all(
        "Payment Entry Reference",
        filters={"parent": pe_name, "reference_doctype": "Sales Invoice"},
        fields=["reference_doctype", "reference_name", "allocated_amount"],
        order_by="idx asc",
    )
    lines = []
    for idx, ref in enumerate(refs, start=1):
        allocated = flt(ref.allocated_amount or 0, 2)
        line = {
            "line_no": idx,
            "reference_doctype": ref.reference_doctype,
            "reference_name": ref.reference_name,
            "allocated_amount": allocated,
            "preview_decision": "Blocked",
            "status": "Blocker",
            "detail": "Referenced Sales Invoice does not exist.",
        }
        if frappe.db.exists("Sales Invoice", ref.reference_name):
            si = frappe.get_doc("Sales Invoice", ref.reference_name)
            outstanding = flt(getattr(si, "outstanding_amount", 0), 2)
            valid = si.docstatus == 1 and outstanding >= allocated and allocated > 0
            line.update(
                {
                    "customer": getattr(si, "customer", None),
                    "company": getattr(si, "company", None),
                    "posting_date": getattr(si, "posting_date", None),
                    "due_date": getattr(si, "due_date", None),
                    "outstanding_amount": outstanding,
                    "status": "Pass" if valid else "Blocker",
                    "preview_decision": "Included" if valid else "Blocked",
                    "detail": (
                        f"Preview allocation {allocated:.2f} against outstanding {outstanding:.2f}."
                        if valid
                        else f"Invoice not valid for preview. docstatus={si.docstatus}, outstanding={outstanding:.2f}, allocated={allocated:.2f}."
                    ),
                }
            )
        lines.append(line)
    return lines


def validate_lines(lines, gate):
    issues = []
    expected_count = int(gate.requested_batch_line_count or 0)
    expected_total = flt(gate.requested_batch_amount or 0, 2)
    total = flt(sum(flt(line.get("allocated_amount") or 0, 2) for line in lines), 2)
    customers = sorted(set(line.get("customer") for line in lines if line.get("customer")))
    companies = sorted(set(line.get("company") for line in lines if line.get("company")))

    if len(lines) != expected_count:
        issues.append(f"Preview line count must be {expected_count}; found {len(lines)}.")
    if total != expected_total:
        issues.append(f"Preview total amount must be {expected_total:.2f}; found {total:.2f}.")
    blockers = [line for line in lines if line.get("status") == "Blocker"]
    if blockers:
        issues.append(f"Preview has blocked reference lines: {len(blockers)}.")
    if len(customers) != 1:
        issues.append(f"Preview lines must use exactly one customer. Found: {customers}")
    if len(companies) != 1:
        issues.append(f"Preview lines must use exactly one company. Found: {companies}")

    for fieldname, expected, label in [
        ("requested_payment_entry_count", 1, "Requested Payment Entry count"),
        ("requested_live_posting", 0, "Requested live posting"),
        ("requested_journal_entry_side_effect", 0, "Requested Journal Entry side effect"),
        ("requested_purchase_invoice_side_effect", 0, "Requested Purchase Invoice side effect"),
    ]:
        if int(getattr(gate, fieldname, 0) or 0) != expected:
            issues.append(f"{label} must be {expected}.")

    return issues, total, customers[0] if len(customers) == 1 else None, companies[0] if len(companies) == 1 else None


def validate_source(gate, guard, policy_enabled, policy_live, config):
    if not gate:
        return ["No approved Phase 10T pre-execution gate found."]
    issues = []
    existing = existing_preview(gate.name)
    if existing:
        issues.append(f"Phase 10U preview already exists for this pre-execution gate: {existing.preview_id}")
    required_links = {
        "pre_execution_gate": (GATE_DOCTYPE, gate.name),
        "readiness": ("NDIS Governed Limited Ops Readiness", gate.readiness),
        "governance_closeout": ("NDIS Runtime Watch Governance Closeout", gate.governance_closeout),
        "freeze": ("NDIS Runtime Watch Violation Sim Freeze", gate.freeze),
        "simulation": ("NDIS Runtime Watch Violation Sim", gate.simulation),
        "runtime_watch": ("NDIS Controlled Limited Ops Runtime Watch", gate.runtime_watch),
        "baseline": ("NDIS Controlled Limited Ops Baseline", gate.baseline),
        "target_policy": (POLICY_DOCTYPE, gate.target_policy),
    }
    for label, (doctype, name) in required_links.items():
        if not name:
            issues.append(f"Missing evidence link: {label}")
        elif not frappe.db.exists(doctype, name):
            issues.append(f"Linked evidence does not exist: {doctype} {name}")
    checks = [
        (policy_enabled == 1, "Target policy production_batch_enabled must be 1 before Phase 10U. Phase 10U must not repair this."),
        (policy_live == 0, "Target policy live_posting_allowed must be 0 before Phase 10U. Phase 10U must not repair this."),
        (guard["production_batch_enabled_policy_count"] == 1, "Exactly one controlled production batch policy must remain enabled."),
        (guard["live_posting_allowed_policy_count"] == 0, "Controlled production live allowed policy count must remain 0."),
        (guard["submitted_journal_entry_count_today"] == 0, "Submitted Journal Entry count today must remain 0."),
        (guard["purchase_invoice_count_today"] == 0, "Purchase Invoice count today must remain 0."),
        (int(config["production_mode"]) == 0, "Production mode config must remain 0."),
        (int(config["live_pe_enabled"]) == 0, "Live Payment Entry posting config must remain 0."),
    ]
    issues.extend(message for ok, message in checks if not ok)
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


def build_audit_items(gate, source_issues, line_issues, ack_ok, lines):
    items = []
    if gate:
        add_item(items, "Pass", "Low", "Evidence", "phase10t_pre_execution_gate_exists", "Phase 10T pre-execution gate exists", f"Pre-execution gate found: {gate.pre_execution_id}.", GATE_DOCTYPE, gate.name)
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase10t_pre_execution_gate_exists", "Phase 10T pre-execution gate exists", "No approved Phase 10T pre-execution gate found.")
    if source_issues:
        for issue in source_issues:
            add_item(items, "Blocker", "Critical", "Preview Source", "preview_source_valid", "Preview source valid", issue)
    else:
        add_item(items, "Pass", "Low", "Preview Source", "preview_source_valid", "Preview source valid", "Phase 10T pre-execution gate is valid for preview.")
    if line_issues:
        for issue in line_issues:
            add_item(items, "Blocker", "Critical", "Preview Shape", "preview_lines_valid", "Preview lines valid", issue)
    else:
        add_item(items, "Pass", "High", "Preview Shape", "preview_lines_valid", "Preview lines valid", "Three preview references total exactly $3.00.")
    for line in lines:
        add_item(items, line.get("status", "Info"), "High" if line.get("status") == "Pass" else "Critical", "Preview Reference", f"preview_line_{line.get('line_no')}", f"Preview line {line.get('line_no')}", line.get("detail"), line.get("reference_doctype"), line.get("reference_name"))
    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {PREVIEW_ACK}")
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
    return max(0, round(100 - int(blockers or 0) * 25 - int(warnings or 0) * 5, 2))


def create_preview_lines(doc, lines):
    for line in lines:
        row = frappe.new_doc(PREVIEW_ITEM_DOCTYPE)
        row.preview = doc.name
        for key, value in line.items():
            if row.meta.has_field(key):
                setattr(row, key, value)
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_governed_limited_operation_preview(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_governed_limited_operation_preview")
    gate = latest_pre_execution_gate()
    guard_before = guardrails()
    ack_ok = acknowledgement == PREVIEW_ACK
    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }
    policy_enabled_before = get_flag(POLICY_DOCTYPE, gate.target_policy, "production_batch_enabled") if gate else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, gate.target_policy, "live_posting_allowed") if gate else 0
    source_issues = validate_source(gate, guard_before, policy_enabled_before, policy_live_before, config)

    source_pe = candidate_payment_entry()
    lines = build_preview_lines_from_payment_entry(source_pe.name) if source_pe else []
    if not source_pe:
        source_issues.append("No cancelled three-line/$3 Payment Entry template found for preview references.")

    line_issues, preview_total, preview_customer, preview_company = validate_lines(lines, gate) if gate else (["No Phase 10T gate."], 0, None, None)
    guard_after = guardrails()
    policy_enabled_after = get_flag(POLICY_DOCTYPE, gate.target_policy, "production_batch_enabled") if gate else 0
    policy_live_after = get_flag(POLICY_DOCTYPE, gate.target_policy, "live_posting_allowed") if gate else 0
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
        source_issues.append("Accounting movement changed while preparing Phase 10U preview evidence.")

    operation_shape_verified = int(
        gate
        and not line_issues
        and int(gate.requested_batch_line_count or 0) == 3
        and flt(gate.requested_batch_amount or 0, 2) == 3
        and int(gate.requested_payment_entry_count or 0) == 1
        and int(gate.requested_live_posting or 0) == 0
        and int(gate.requested_journal_entry_side_effect or 0) == 0
        and int(gate.requested_purchase_invoice_side_effect or 0) == 0
    )
    items = build_audit_items(gate, source_issues, line_issues, ack_ok, lines)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and gate and operation_shape_verified and no_new_movement and policy_preserved)

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Previewed" if allowed else "Needs Review",
        "preview_status": "Governed Limited Operation Preview Ready" if allowed else "Needs Review",
        "preview_completed": allowed,
        "operation_previewed": allowed,
        "operation_shape_verified": operation_shape_verified,
        "operation_preview_locked": allowed,
        "ready_for_governed_limited_operation_execution_gate": allowed,
        "pre_execution_gate_verified": 1 if gate else 0,
        "preview_only_verified": 1,
        "no_new_accounting_movement_verified": no_new_movement,
        "policy_state_preserved_verified": policy_preserved,
        "policy_mutation_performed": 0,
        "actual_policy_mutation_count": 0,
        "phase10t_pre_execution_verified": 1 if gate else 0,
        "phase10s_readiness_verified": 1 if gate else 0,
        "phase10r_governance_closeout_verified": 1 if gate else 0,
        "phase10q_freeze_verified": 1 if gate else 0,
        "phase10p_simulation_verified": 1 if gate else 0,
        "phase10o_runtime_watch_verified": 1 if gate else 0,
        "phase10n_baseline_verified": 1 if gate else 0,
        "controlled_policy_enabled_verified": int(policy_enabled_after == 1),
        "live_posting_blocked_verified": int(policy_live_after == 0),
        "pre_execution_gate": gate.name if gate else None,
        "readiness": gate.readiness if gate else None,
        "governance_closeout": gate.governance_closeout if gate else None,
        "freeze": gate.freeze if gate else None,
        "simulation": gate.simulation if gate else None,
        "runtime_watch": gate.runtime_watch if gate else None,
        "baseline": gate.baseline if gate else None,
        "monitoring_register": gate.monitoring_register if gate else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": gate.target_policy if gate else None,
        "target_policy_name": gate.target_policy_name if gate else None,
        "target_policy_enabled_before": policy_enabled_before,
        "target_policy_enabled_after": policy_enabled_after,
        "target_policy_live_before": policy_live_before,
        "target_policy_live_after": policy_live_after,
        "production_batch_enabled_policy_count_before": guard_before["production_batch_enabled_policy_count"],
        "production_batch_enabled_policy_count_after": guard_after["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count_before": guard_before["live_posting_allowed_policy_count"],
        "live_posting_allowed_policy_count_after": guard_after["live_posting_allowed_policy_count"],
        "requested_batch_line_count": int(gate.requested_batch_line_count or 0) if gate else 0,
        "requested_batch_amount": flt(gate.requested_batch_amount or 0, 2) if gate else 0,
        "requested_payment_entry_count": int(gate.requested_payment_entry_count or 0) if gate else 0,
        "requested_live_posting": int(gate.requested_live_posting or 0) if gate else 0,
        "requested_journal_entry_side_effect": int(gate.requested_journal_entry_side_effect or 0) if gate else 0,
        "requested_purchase_invoice_side_effect": int(gate.requested_purchase_invoice_side_effect or 0) if gate else 0,
        "preview_line_count": len(lines),
        "preview_total_amount": preview_total,
        "preview_customer": preview_customer,
        "preview_company": preview_company,
        "source_payment_entry": source_pe.name if source_pe else None,
        "would_create_payment_entry_count": 1 if operation_shape_verified else 0,
        "would_create_gl_entry_count": 0,
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "actual_payment_entry_created_count": 0,
        "actual_payment_entry_cancelled_count": 0,
        "actual_gl_created_count": 0,
        "submitted_journal_entry_count_today": guard_after["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_after["purchase_invoice_count_today"],
        "preview_score": score,
        **item_summary,
        "items": items,
        "preview_lines": lines,
        "source_issues": source_issues,
        "line_issues": line_issues,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "required_acknowledgement": PREVIEW_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 10U builds preview evidence only. No Payment Entry, GL Entry, Journal Entry, Purchase Invoice, or policy mutation is performed.",
    }
    if int(dry_run or 0):
        result.update({"status": "Needs Review", "preview_status": "Needs Review", "preview_completed": 0, "operation_previewed": 0, "operation_preview_locked": 0, "ready_for_governed_limited_operation_execution_gate": 0})
        return result

    doc = frappe.new_doc(PREVIEW_DOCTYPE)
    doc.preview_id = make_preview_id()
    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = PREVIEW_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.preview_json = safe_json({"preview_lines": lines, "source_payment_entry": source_pe, "guardrails_before": guard_before, "guardrails_after": guard_after, "config": config})
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_preview_lines(doc, lines)
    frappe.db.commit()
    return {**result, "created": True, "preview": doc.name, "preview_id": doc.preview_id, "guardrails_after": guardrails()}


@frappe.whitelist()
def cancel_governed_limited_operation_preview_audit(preview, reason=None):
    assert_action("cancel_governed_limited_operation_preview_audit")
    if not frappe.db.exists(PREVIEW_DOCTYPE, preview):
        frappe.throw(_("Governed limited operation preview audit not found: {0}").format(preview))
    doc = frappe.get_doc(PREVIEW_DOCTYPE, preview)
    if doc.status == "Cancelled":
        return {"preview": preview, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.preview_completed or 0):
        frappe.throw(_("Cannot cancel a completed Phase 10U preview record."))
    frappe.db.set_value(
        PREVIEW_DOCTYPE,
        preview,
        {"status": "Cancelled", "preview_status": "Cancelled", "cancelled_on": now_datetime(), "cancelled_by": frappe.session.user, "summary_json": reason or "Phase 10U no-ack preview audit cancelled."},
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{PREVIEW_ITEM_DOCTYPE}` SET status = 'Cancelled' WHERE preview = %(preview)s", {"preview": preview})
    frappe.db.commit()
    return {"preview": preview, "status": "Cancelled", "note": "No-ack preview audit cancelled only. No accounting or policy movement occurred."}


@frappe.whitelist()
def quick_governed_limited_operation_preview_summary(limit=20):
    records = frappe.get_all(
        PREVIEW_DOCTYPE,
        fields=[
            "name",
            "preview_id",
            "status",
            "preview_status",
            "preview_completed",
            "operation_previewed",
            "operation_shape_verified",
            "ready_for_governed_limited_operation_execution_gate",
            "pre_execution_gate",
            "readiness",
            "runtime_watch",
            "preview_line_count",
            "preview_total_amount",
            "preview_customer",
            "preview_company",
            "source_payment_entry",
            "would_create_payment_entry_count",
            "would_create_gl_entry_count",
            "production_batch_enabled_policy_count_after",
            "live_posting_allowed_policy_count_after",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "submitted_journal_entry_count_today",
            "purchase_invoice_count_today",
            "preview_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        PREVIEW_ITEM_DOCTYPE,
        fields=["name", "preview", "line_no", "status", "reference_doctype", "reference_name", "customer", "company", "outstanding_amount", "allocated_amount", "preview_decision", "detail"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {"previews": records, "items": items, "required_acknowledgement": PREVIEW_ACK, "guardrails": guardrails(), "note": "Phase 10U preview summary. Previewed record allows the next execution gate only."}


def execute_preview_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("p.status = %(status)s")
        params["status"] = filters.get("status")
    data = frappe.db.sql(
        f"""
        SELECT
            p.name AS preview,
            p.preview_id,
            p.status,
            p.preview_status,
            p.preview_completed,
            p.operation_previewed,
            p.operation_shape_verified,
            p.ready_for_governed_limited_operation_execution_gate,
            p.pre_execution_gate,
            p.readiness,
            p.runtime_watch,
            p.preview_line_count,
            p.preview_total_amount,
            p.preview_customer,
            p.preview_company,
            p.source_payment_entry,
            p.would_create_payment_entry_count,
            p.would_create_gl_entry_count,
            p.production_batch_enabled_policy_count_after,
            p.live_posting_allowed_policy_count_after,
            p.payment_entry_count_before,
            p.payment_entry_count_after,
            p.payment_entry_gl_count_before,
            p.payment_entry_gl_count_after,
            p.submitted_journal_entry_count_today,
            p.purchase_invoice_count_today,
            p.preview_score,
            p.checked_on,
            %(currency)s AS currency
        FROM `tab{PREVIEW_DOCTYPE}` p
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
                {"name": "Previewed", "values": [int(row.preview_completed or 0) for row in data[:20]]},
                {"name": "Would Create PE", "values": [int(row.would_create_payment_entry_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Previews"), "datatype": "Int"},
        {"value": sum(int(row.preview_completed or 0) for row in data), "indicator": "Green", "label": _("Previewed"), "datatype": "Int"},
        {"value": sum(int(row.would_create_payment_entry_count or 0) for row in data), "indicator": "Orange", "label": _("Would Create PE"), "datatype": "Int"},
        {"value": sum(int(row.would_create_gl_entry_count or 0) for row in data), "indicator": "Red", "label": _("Would Create GL"), "datatype": "Int"},
    ]
    return preview_columns(), data, None, chart, summary


def preview_columns():
    return [
        {"fieldname": "preview", "label": _("Preview"), "fieldtype": "Link", "options": PREVIEW_DOCTYPE, "width": 220},
        {"fieldname": "preview_id", "label": _("Preview ID"), "fieldtype": "Data", "width": 390},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "preview_status", "label": _("Preview Status"), "fieldtype": "Data", "width": 320},
        {"fieldname": "preview_completed", "label": _("Previewed"), "fieldtype": "Check", "width": 90},
        {"fieldname": "operation_previewed", "label": _("Op Previewed"), "fieldtype": "Check", "width": 105},
        {"fieldname": "operation_shape_verified", "label": _("Shape OK"), "fieldtype": "Check", "width": 90},
        {"fieldname": "ready_for_governed_limited_operation_execution_gate", "label": _("Ready Exec Gate"), "fieldtype": "Check", "width": 120},
        {"fieldname": "pre_execution_gate", "label": _("Pre-Execution Gate"), "fieldtype": "Link", "options": GATE_DOCTYPE, "width": 220},
        {"fieldname": "readiness", "label": _("Readiness"), "fieldtype": "Link", "options": "NDIS Governed Limited Ops Readiness", "width": 220},
        {"fieldname": "runtime_watch", "label": _("Runtime Watch"), "fieldtype": "Link", "options": "NDIS Controlled Limited Ops Runtime Watch", "width": 220},
        {"fieldname": "preview_line_count", "label": _("Lines"), "fieldtype": "Int", "width": 75},
        {"fieldname": "preview_total_amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 105},
        {"fieldname": "preview_customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 180},
        {"fieldname": "preview_company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 180},
        {"fieldname": "source_payment_entry", "label": _("Source PE"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "would_create_payment_entry_count", "label": _("Would PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "would_create_gl_entry_count", "label": _("Would GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "production_batch_enabled_policy_count_after", "label": _("Enabled Policies"), "fieldtype": "Int", "width": 125},
        {"fieldname": "live_posting_allowed_policy_count_after", "label": _("Live Policies"), "fieldtype": "Int", "width": 105},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 85},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 110},
        {"fieldname": "submitted_journal_entry_count_today", "label": _("JE Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "purchase_invoice_count_today", "label": _("PI Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "preview_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("preview"):
        conditions.append("i.preview = %(preview)s")
        params["preview"] = filters.get("preview")
    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")
    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item,
            i.preview,
            i.line_no,
            i.status,
            i.reference_doctype,
            i.reference_name,
            i.customer,
            i.company,
            i.outstanding_amount,
            i.allocated_amount,
            i.preview_decision,
            i.detail,
            i.checked_on,
            %(currency)s AS currency
        FROM `tab{PREVIEW_ITEM_DOCTYPE}` i
        {build_where(conditions)}
        ORDER BY i.preview DESC, i.line_no ASC, i.creation DESC
        """,
        params,
        as_dict=True,
    )
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": PREVIEW_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "preview", "label": _("Preview"), "fieldtype": "Link", "options": PREVIEW_DOCTYPE, "width": 220},
        {"fieldname": "line_no", "label": _("Line"), "fieldtype": "Int", "width": 70},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "reference_doctype", "label": _("Reference DocType"), "fieldtype": "Data", "width": 150},
        {"fieldname": "reference_name", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 190},
        {"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 180},
        {"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 180},
        {"fieldname": "outstanding_amount", "label": _("Outstanding"), "fieldtype": "Currency", "options": "currency", "width": 105},
        {"fieldname": "allocated_amount", "label": _("Allocated"), "fieldtype": "Currency", "options": "currency", "width": 105},
        {"fieldname": "preview_decision", "label": _("Decision"), "fieldtype": "Data", "width": 90},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 450},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    chart = {"data": {"labels": [str(row.reference_name) for row in data[:20]], "datasets": [{"name": "Allocated", "values": [flt(row.allocated_amount or 0, 2) for row in data[:20]]}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Preview Lines"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Pass"]), "indicator": "Green", "label": _("Pass"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
        {"value": sum(flt(row.allocated_amount or 0, 2) for row in data), "indicator": "Green", "label": _("Allocated Total"), "datatype": "Currency", "currency": currency()},
    ]
    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_preview_report(filters)
    guard = guardrails()
    summary.extend(
        [
            {"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"},
            {"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"},
            {"value": guard["production_batch_enabled_policy_count"], "indicator": "Green", "label": _("Enabled Policies"), "datatype": "Int"},
            {"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Policies"), "datatype": "Int"},
            {"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"},
            {"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"},
        ]
    )
    return columns, data, message, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
