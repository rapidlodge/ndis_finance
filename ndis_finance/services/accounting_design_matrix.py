import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


DESIGN_ACK = "I_CONFIRM_NDIS_CONTROLLED_ACCOUNTING_DESIGN_REVIEWED"

REQUIRED_EVENT_TYPES = [
    "Claim Batch",
    "Remittance",
    "Recovery Receipt",
    "Recovery Write Off",
    "Payroll Cost Import",
    "Cost Pool Allocation",
    "Governance Pack",
    "Xero Export",
]

PHASE_HEALTH_CHECKS = [
    ("Phase 2F", "ndis_finance.setup.phase2f.health_check"),
    ("Phase 2E", "ndis_finance.setup.phase2e.health_check"),
    ("Phase 2D", "ndis_finance.setup.phase2d.health_check"),
    ("Phase 2C", "ndis_finance.setup.phase2c.health_check"),
    ("Phase 2B", "ndis_finance.setup.phase2b.health_check"),
    ("Phase 2A", "ndis_finance.setup.phase2a.health_check"),
]


def make_review_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-ACC-DESIGN-REVIEW-{timestamp}-{frappe.generate_hash(length=5).upper()}"


def safe_json(value):
    try:
        return json.dumps(value, indent=2, default=str)
    except Exception:
        return str(value)


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


def health_check_is_green(result):
    green_keys = [
        "doctypes",
        "reports",
        "default_matrix",
        "journal_entry_custom_fields",
        "workspace_shortcuts",
        "js_hooks",
        "list_js_hooks",
        "report_files",
    ]
    for key in green_keys:
        if key in result and not all_nested_truthy(result[key]):
            return False
    if "service_import" in result and not result["service_import"]:
        return False
    if int(result.get("production_mode_detected") or 0):
        return False
    return True


def all_nested_truthy(value):
    if isinstance(value, dict):
        return all(all_nested_truthy(child) for child in value.values())
    if isinstance(value, list):
        return all(all_nested_truthy(child) for child in value)
    return bool(value)


def evaluate_phase_dependencies(items):
    for label, method_path in PHASE_HEALTH_CHECKS:
        try:
            result = frappe.get_attr(method_path)()
            if health_check_is_green(result):
                add_item(items, "Pass", "Low", "Phase Dependency", method_path, f"{label} health check", "Health check is green.")
            else:
                add_item(items, "Blocker", "Critical", "Phase Dependency", method_path, f"{label} health check", "Health check returned non-green control fields.", "Fix previous phase health checks before approving accounting design matrix.")
        except Exception as exc:
            add_item(items, "Blocker", "Critical", "Phase Dependency", method_path, f"{label} health check", f"Health check failed: {str(exc)}", "Fix failed previous phase health check.")


def evaluate_site_config(items):
    sandbox_enabled = int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0)
    production_mode = int(frappe.conf.get("ndis_finance_production_mode") or 0)
    add_item(items, "Pass" if sandbox_enabled else "Warning", "Low" if sandbox_enabled else "Medium", "Site Config", "sandbox_config", "Sandbox posting config", "Sandbox posting config is enabled." if sandbox_enabled else "Sandbox posting config is not enabled.", None if sandbox_enabled else "Enable sandbox config only in dev/test when testing adapters.")
    add_item(items, "Blocker" if production_mode else "Pass", "Critical" if production_mode else "Low", "Site Config", "production_mode", "Production mode", "Production mode flag is enabled." if production_mode else "Production mode is not enabled.", "Do not design/test posting adapters while production mode is enabled." if production_mode else None)
    return sandbox_enabled, production_mode


def latest_allowed_sandbox_completion_gate():
    rows = frappe.get_all(
        "NDIS Accounting Sandbox Completion Gate",
        filters={"sandbox_completion_allowed": 1, "status": ["in", ["Passed", "Needs Review"]]},
        fields=["name", "gate_id", "completion_score", "sandbox_completion_allowed"],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def evaluate_sandbox_completion(items):
    gate = latest_allowed_sandbox_completion_gate()
    if gate:
        add_item(items, "Pass", "Low", "Sandbox Completion", "sandbox_completion_gate", "Allowed sandbox completion gate", f"Allowed sandbox completion gate found with score {gate.completion_score}.", None, "NDIS Accounting Sandbox Completion Gate", gate.name)
        return gate
    add_item(items, "Blocker", "Critical", "Sandbox Completion", "sandbox_completion_gate", "Allowed sandbox completion gate", "No allowed sandbox completion gate found.", "Run and acknowledge Phase 2F before approving accounting design matrix.")
    return None


def get_matrix_rows():
    return frappe.get_all(
        "NDIS Accounting Design Matrix",
        fields=[
            "name",
            "matrix_id",
            "design_name",
            "design_status",
            "risk_level",
            "event_type",
            "source_doctype",
            "accounting_treatment",
            "allowed_target_doctype",
            "posting_route",
            "live_posting_allowed_later",
            "direct_gl_allowed",
            "payment_entry_allowed_later",
            "journal_entry_allowed_later",
            "sales_invoice_allowed_later",
            "xero_export_allowed_later",
            "requires_readiness_gate",
            "requires_sandbox_completion_gate",
            "requires_governance_pack",
            "requires_cfo_approval",
            "requires_duplicate_check",
            "requires_reversal_plan",
            "duplicate_prevention_rule",
            "failure_handling_rule",
            "rollback_rule",
        ],
        order_by="event_type asc, design_name asc",
        limit=10000,
    )


def evaluate_matrix_coverage(items):
    rows = get_matrix_rows()
    event_types = {row.event_type for row in rows if row.design_status in ["Active", "Draft"]}
    missing = [event for event in REQUIRED_EVENT_TYPES if event not in event_types]
    if missing:
        add_item(items, "Blocker", "Critical", "Matrix Coverage", "required_event_coverage", "Required event coverage", "Missing design matrix event type(s): " + ", ".join(missing), "Add design matrix rows before future accounting adapter design.")
    else:
        add_item(items, "Pass", "Low", "Matrix Coverage", "required_event_coverage", "Required event coverage", "All required accounting design event types are covered.")

    active_count = len([row for row in rows if row.design_status == "Active"])
    draft_count = len([row for row in rows if row.design_status == "Draft"])
    add_item(items, "Pass" if active_count >= 7 else "Warning", "Low" if active_count >= 7 else "Medium", "Matrix Coverage", "active_matrix_count", "Active design matrix rows", f"{active_count} active design matrix row(s) found.", None if active_count >= 7 else "Review draft/suspended rows before future live adapter design.")
    add_item(items, "Info" if draft_count else "Pass", "Low", "Matrix Coverage", "draft_matrix_count", "Draft design matrix rows", f"{draft_count} draft design matrix row(s) found." if draft_count else "No draft design rows found.")
    return rows, active_count, draft_count


def evaluate_matrix_safety(items, rows):
    unsafe_count = 0
    for row in rows:
        if int(row.direct_gl_allowed or 0):
            unsafe_count += 1
            add_item(items, "Blocker", "Critical", "Matrix Safety", "direct_gl_allowed", "Direct GL allowed", f"{row.design_name} allows direct GL. This is not permitted.", "Disable direct_gl_allowed.", "NDIS Accounting Design Matrix", row.name)
        if row.allowed_target_doctype == "GL Entry":
            unsafe_count += 1
            add_item(items, "Blocker", "Critical", "Matrix Safety", "target_gl_entry", "GL Entry target selected", f"{row.design_name} has GL Entry as target. This is not permitted.", "Use controlled ERPNext document types only.", "NDIS Accounting Design Matrix", row.name)
        if row.event_type in ["Payroll Cost Import", "Cost Pool Allocation"] and row.allowed_target_doctype != "None":
            unsafe_count += 1
            add_item(items, "Blocker", "Critical", "Duplication Prevention", "management_only_target", "Management-only event has accounting target", f"{row.design_name} should be management-only but target is {row.allowed_target_doctype}.", "Set allowed target to None.", "NDIS Accounting Design Matrix", row.name)
        if row.event_type == "Payroll Cost Import" and (int(row.payment_entry_allowed_later or 0) or int(row.journal_entry_allowed_later or 0) or int(row.sales_invoice_allowed_later or 0)):
            unsafe_count += 1
            add_item(items, "Blocker", "Critical", "Payroll Duplication", "payroll_accounting_duplicate_risk", "Payroll accounting duplication risk", f"{row.design_name} has future accounting flags enabled.", "NDIS payroll costing must not duplicate AU Payroll / HRMS accounting.", "NDIS Accounting Design Matrix", row.name)
        if int(row.live_posting_allowed_later or 0):
            add_item(items, "Warning", "High", "Matrix Safety", "live_posting_future_flag", "Live posting future flag", f"{row.design_name} has live_posting_allowed_later enabled.", "Keep this disabled until a future production activation gate.", "NDIS Accounting Design Matrix", row.name)

        required_texts = {"duplicate_prevention_rule": row.duplicate_prevention_rule, "failure_handling_rule": row.failure_handling_rule}
        if int(row.requires_reversal_plan or 0):
            required_texts["rollback_rule"] = row.rollback_rule
        for fieldname, value in required_texts.items():
            if not value:
                add_item(items, "Warning", "Medium", "Matrix Completeness", fieldname, f"Missing {fieldname}", f"{row.design_name} is missing {fieldname}.", "Complete all design control rules.", "NDIS Accounting Design Matrix", row.name)

    if not unsafe_count:
        add_item(items, "Pass", "Low", "Matrix Safety", "unsafe_design_rows", "Unsafe design rows", "No unsafe accounting design rows found.")
    return unsafe_count


def evaluate_policy_coverage(items):
    policies = frappe.get_all(
        "NDIS Accounting Posting Policy",
        filters={"active": 1, "policy_status": "Active"},
        fields=["name", "policy_id", "event_type", "source_doctype"],
        limit=10000,
    )
    covered = 0
    missing = []
    for policy in policies:
        matrix = frappe.get_all(
            "NDIS Accounting Design Matrix",
            filters={"event_type": policy.event_type, "source_doctype": policy.source_doctype, "design_status": ["in", ["Active", "Draft"]]},
            fields=["name"],
            limit=1,
        )
        if matrix:
            covered += 1
        else:
            missing.append(policy.policy_id)
    if missing:
        add_item(items, "Blocker", "Critical", "Policy Coverage", "policy_design_coverage", "Posting policy design coverage", "Missing design coverage for policies: " + ", ".join(missing), "Every active posting policy must have a design matrix row.")
    else:
        add_item(items, "Pass", "Low", "Policy Coverage", "policy_design_coverage", "Posting policy design coverage", f"All {len(policies)} active posting policies have design matrix coverage.")
    return covered, len(missing)


def evaluate_movement_guardrails(items):
    counts = {
        "Payment Entry": frappe.db.count("Payment Entry", {"creation": [">=", today()]}) if frappe.db.exists("DocType", "Payment Entry") else 0,
        "Submitted Journal Entry": frappe.db.count("Journal Entry", {"creation": [">=", today()], "docstatus": 1}) if frappe.db.exists("DocType", "Journal Entry") else 0,
        "GL Entry": frappe.db.count("GL Entry", {"creation": [">=", today()]}) if frappe.db.exists("DocType", "GL Entry") else 0,
        "Sales Invoice": frappe.db.count("Sales Invoice", {"creation": [">=", today()]}) if frappe.db.exists("DocType", "Sales Invoice") else 0,
        "Purchase Invoice": frappe.db.count("Purchase Invoice", {"creation": [">=", today()]}) if frappe.db.exists("DocType", "Purchase Invoice") else 0,
    }
    total = sum(int(value or 0) for value in counts.values())
    add_item(items, "Warning" if total else "Pass", "Medium" if total else "Low", "Movement Guardrail", "movement_counts_today", "Accounting movement counts today", "Today counts: " + ", ".join([f"{key}={value}" for key, value in counts.items()]) if total else "No Payment Entry, submitted Journal Entry, GL Entry, Sales Invoice or Purchase Invoice created today.", "Confirm these are unrelated to Phase 3A because Phase 3A must not create accounting movement." if total else None)
    return counts


def summarise_items(items):
    return {
        "blocker_count": len([i for i in items if i["status"] == "Blocker"]),
        "warning_count": len([i for i in items if i["status"] == "Warning"]),
        "pass_count": len([i for i in items if i["status"] == "Pass"]),
        "info_count": len([i for i in items if i["status"] == "Info"]),
        "item_count": len(items),
    }


@frappe.whitelist()
def run_accounting_design_review(review_type="Controlled Accounting Design Matrix", acknowledgement=None, dry_run=0, notes=None):
    assert_action("run_accounting_design_review")
    items = []
    sandbox_config_enabled, production_mode_detected = evaluate_site_config(items)
    evaluate_phase_dependencies(items)
    completion_gate = evaluate_sandbox_completion(items)
    matrix_rows, active_matrix_count, draft_matrix_count = evaluate_matrix_coverage(items)
    unsafe_matrix_count = evaluate_matrix_safety(items, matrix_rows)
    policy_coverage_count, missing_policy_coverage_count = evaluate_policy_coverage(items)
    movement_counts = evaluate_movement_guardrails(items)
    ack_ok = acknowledgement == DESIGN_ACK
    add_item(
        items,
        "Pass" if ack_ok else "Warning",
        "Low" if ack_ok else "Medium",
        "Acknowledgement",
        "design_ack",
        "Design acknowledgement",
        "Exact acknowledgement supplied." if ack_ok else f"Required acknowledgement not supplied. Required: {DESIGN_ACK}",
        None if ack_ok else "Provide exact acknowledgement to approve design for next phase.",
    )
    summary = summarise_items(items)
    design_approved = int(summary["blocker_count"] == 0 and ack_ok)
    status = "Blocked" if summary["blocker_count"] else ("Needs Review" if summary["warning_count"] or not ack_ok else "Passed")
    result = {
        "dry_run": bool(int(dry_run or 0)),
        "review_type": review_type,
        "status": status,
        "design_approved_for_next_phase": design_approved,
        "required_acknowledgement": DESIGN_ACK,
        "acknowledgement_ok": ack_ok,
        "summary": summary,
        "matrix_counts": {
            "matrix_count": len(matrix_rows),
            "active_matrix_count": active_matrix_count,
            "draft_matrix_count": draft_matrix_count,
            "unsafe_matrix_count": unsafe_matrix_count,
            "policy_coverage_count": policy_coverage_count,
            "missing_policy_coverage_count": missing_policy_coverage_count,
        },
        "sandbox_completion_gate": completion_gate,
        "movement_counts": movement_counts,
        "items": items,
        "note": "Controlled accounting design review only. No Payment Entry, Journal Entry, GL Entry, Sales Invoice, Purchase Invoice, payroll posting, STP, ABA, email, Xero export, bank allocation, or payment movement created.",
    }
    if int(dry_run or 0):
        return result

    doc = frappe.new_doc("NDIS Accounting Design Review")
    doc.review_id = make_review_id()
    doc.review_type = review_type
    doc.status = status
    doc.design_approved_for_next_phase = design_approved
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = sandbox_config_enabled
    doc.production_mode_detected = production_mode_detected
    doc.reviewed_on = now_datetime()
    doc.reviewed_by = frappe.session.user
    doc.blocker_count = summary["blocker_count"]
    doc.warning_count = summary["warning_count"]
    doc.pass_count = summary["pass_count"]
    doc.info_count = summary["info_count"]
    doc.item_count = summary["item_count"]
    doc.matrix_count = len(matrix_rows)
    doc.active_matrix_count = active_matrix_count
    doc.draft_matrix_count = draft_matrix_count
    doc.unsafe_matrix_count = unsafe_matrix_count
    doc.policy_coverage_count = policy_coverage_count
    doc.missing_policy_coverage_count = missing_policy_coverage_count
    doc.sandbox_completion_gate = completion_gate.name if completion_gate else None
    doc.sandbox_completion_allowed = int(completion_gate.sandbox_completion_allowed or 0) if completion_gate else 0
    doc.completion_score = flt(completion_gate.completion_score) if completion_gate else 0
    doc.required_acknowledgement = DESIGN_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    exception_count_by_matrix = {}
    for item in items:
        row = frappe.new_doc("NDIS Accounting Design Review Item")
        row.design_review = doc.name
        row.status = item["status"]
        row.severity = item["severity"]
        row.category = item["category"]
        row.check_key = item["check_key"]
        row.check_label = item["check_label"]
        row.detail = item["detail"]
        row.recommendation = item.get("recommendation")
        row.source_doctype = item.get("source_doctype")
        row.source_name = item.get("source_name")
        row.reviewed_on = doc.reviewed_on
        row.insert(ignore_permissions=True)
        if item.get("source_doctype") == "NDIS Accounting Design Matrix" and item.get("source_name") and item["status"] in ["Blocker", "Warning"]:
            exception_count_by_matrix[item["source_name"]] = exception_count_by_matrix.get(item["source_name"], 0) + 1

    for row in matrix_rows:
        frappe.db.set_value(
            "NDIS Accounting Design Matrix",
            row.name,
            {"last_review": doc.name, "last_review_on": doc.reviewed_on, "review_exception_count": exception_count_by_matrix.get(row.name, 0)},
            update_modified=False,
        )
    frappe.db.commit()
    result["created"] = True
    result["design_review"] = doc.name
    result["review_id"] = doc.review_id
    return result


@frappe.whitelist()
def cancel_accounting_design_review(design_review, reason=None):
    assert_action("cancel_accounting_design_review")
    if not frappe.db.exists("NDIS Accounting Design Review", design_review):
        frappe.throw(_("Accounting Design Review not found: {0}").format(design_review))
    frappe.db.set_value(
        "NDIS Accounting Design Review",
        design_review,
        {
            "status": "Cancelled",
            "design_approved_for_next_phase": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "warning_log": reason or "Accounting design review cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        """
        UPDATE `tabNDIS Accounting Design Review Item`
        SET status = 'Cancelled'
        WHERE design_review = %(design_review)s
        """,
        {"design_review": design_review},
    )
    frappe.db.commit()
    return {"design_review": design_review, "status": "Cancelled", "note": "Design review cancelled only. No accounting/payroll/payment/Xero records were changed."}


@frappe.whitelist()
def quick_accounting_design_summary(limit=20):
    matrix = frappe.get_all(
        "NDIS Accounting Design Matrix",
        fields=["name", "matrix_id", "design_name", "design_status", "risk_level", "event_type", "source_doctype", "accounting_treatment", "allowed_target_doctype", "posting_route", "direct_gl_allowed", "payment_entry_allowed_later", "journal_entry_allowed_later", "sales_invoice_allowed_later", "xero_export_allowed_later", "review_exception_count", "last_review_on"],
        order_by="event_type asc, design_name asc",
        limit=int(limit or 20),
    )
    reviews = frappe.get_all(
        "NDIS Accounting Design Review",
        fields=["name", "review_id", "status", "design_approved_for_next_phase", "blocker_count", "warning_count", "matrix_count", "active_matrix_count", "unsafe_matrix_count", "missing_policy_coverage_count", "reviewed_on"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "matrix": matrix,
        "reviews": reviews,
        "required_acknowledgement": DESIGN_ACK,
        "note": "Accounting design summary only. No accounting, payroll, STP, ABA, email, Xero export, bank allocation, or payment movement created.",
    }


def execute_design_matrix_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    for field in ["event_type", "design_status", "risk_level", "allowed_target_doctype"]:
        if filters.get(field):
            conditions.append(f"m.{field} = %({field})s")
            params[field] = filters.get(field)
    columns = [
        {"fieldname": "matrix", "label": _("Matrix"), "fieldtype": "Link", "options": "NDIS Accounting Design Matrix", "width": 220},
        {"fieldname": "matrix_id", "label": _("Matrix ID"), "fieldtype": "Data", "width": 290},
        {"fieldname": "design_name", "label": _("Design Name"), "fieldtype": "Data", "width": 320},
        {"fieldname": "design_status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "risk_level", "label": _("Risk"), "fieldtype": "Data", "width": 90},
        {"fieldname": "event_type", "label": _("Event Type"), "fieldtype": "Data", "width": 160},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 210},
        {"fieldname": "accounting_treatment", "label": _("Treatment"), "fieldtype": "Data", "width": 240},
        {"fieldname": "allowed_target_doctype", "label": _("Target"), "fieldtype": "Data", "width": 130},
        {"fieldname": "posting_route", "label": _("Route"), "fieldtype": "Data", "width": 220},
        {"fieldname": "direct_gl_allowed", "label": _("Direct GL"), "fieldtype": "Check", "width": 80},
        {"fieldname": "payment_entry_allowed_later", "label": _("PE Later"), "fieldtype": "Check", "width": 80},
        {"fieldname": "journal_entry_allowed_later", "label": _("JE Later"), "fieldtype": "Check", "width": 80},
        {"fieldname": "xero_export_allowed_later", "label": _("Xero Later"), "fieldtype": "Check", "width": 90},
        {"fieldname": "review_exception_count", "label": _("Exceptions"), "fieldtype": "Int", "width": 90},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            m.name AS matrix, m.matrix_id, m.design_name, m.design_status, m.risk_level,
            m.event_type, m.source_doctype, m.accounting_treatment, m.allowed_target_doctype,
            m.posting_route, m.direct_gl_allowed, m.payment_entry_allowed_later,
            m.journal_entry_allowed_later, m.xero_export_allowed_later, m.review_exception_count
        FROM `tabNDIS Accounting Design Matrix` m
        {build_where(conditions)}
        ORDER BY m.event_type ASC, m.design_name ASC
        """,
        params,
        as_dict=True,
    )
    chart_map = {}
    for row in data:
        key = row.allowed_target_doctype or "None"
        chart_map[key] = chart_map.get(key, 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Design Rows", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Design Rows"), "datatype": "Int"},
        {"value": len([row for row in data if row.design_status == "Active"]), "indicator": "Green", "label": _("Active"), "datatype": "Int"},
        {"value": len([row for row in data if row.direct_gl_allowed]), "indicator": "Red", "label": _("Direct GL Allowed"), "datatype": "Int"},
        {"value": len([row for row in data if row.xero_export_allowed_later]), "indicator": "Orange", "label": _("Xero Future"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_design_review_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("status"):
        conditions.append("r.status = %(status)s")
        params["status"] = filters.get("status")
    if filters.get("design_approved_for_next_phase") not in [None, ""]:
        conditions.append("r.design_approved_for_next_phase = %(approved)s")
        params["approved"] = int(filters.get("design_approved_for_next_phase"))
    if filters.get("from_date"):
        conditions.append("DATE(r.reviewed_on) >= %(from_date)s")
        params["from_date"] = filters.get("from_date")
    if filters.get("to_date"):
        conditions.append("DATE(r.reviewed_on) <= %(to_date)s")
        params["to_date"] = filters.get("to_date")
    columns = [
        {"fieldname": "design_review", "label": _("Design Review"), "fieldtype": "Link", "options": "NDIS Accounting Design Review", "width": 220},
        {"fieldname": "review_id", "label": _("Review ID"), "fieldtype": "Data", "width": 320},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "design_approved_for_next_phase", "label": _("Approved"), "fieldtype": "Check", "width": 90},
        {"fieldname": "blocker_count", "label": _("Blockers"), "fieldtype": "Int", "width": 90},
        {"fieldname": "warning_count", "label": _("Warnings"), "fieldtype": "Int", "width": 90},
        {"fieldname": "matrix_count", "label": _("Matrix Rows"), "fieldtype": "Int", "width": 100},
        {"fieldname": "active_matrix_count", "label": _("Active Rows"), "fieldtype": "Int", "width": 100},
        {"fieldname": "unsafe_matrix_count", "label": _("Unsafe Rows"), "fieldtype": "Int", "width": 100},
        {"fieldname": "missing_policy_coverage_count", "label": _("Missing Policy Coverage"), "fieldtype": "Int", "width": 160},
        {"fieldname": "sandbox_completion_gate", "label": _("Sandbox Completion Gate"), "fieldtype": "Link", "options": "NDIS Accounting Sandbox Completion Gate", "width": 220},
        {"fieldname": "completion_score", "label": _("Completion Score"), "fieldtype": "Percent", "width": 120},
        {"fieldname": "reviewed_on", "label": _("Reviewed On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "reviewed_by", "label": _("Reviewed By"), "fieldtype": "Link", "options": "User", "width": 160},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            r.name AS design_review, r.review_id, r.status, r.design_approved_for_next_phase,
            r.blocker_count, r.warning_count, r.matrix_count, r.active_matrix_count,
            r.unsafe_matrix_count, r.missing_policy_coverage_count, r.sandbox_completion_gate,
            r.completion_score, r.reviewed_on, r.reviewed_by
        FROM `tabNDIS Accounting Design Review` r
        {build_where(conditions)}
        ORDER BY r.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.review_id for row in data[:20]],
            "datasets": [
                {"name": "Blockers", "values": [int(row.blocker_count or 0) for row in data[:20]]},
                {"name": "Warnings", "values": [int(row.warning_count or 0) for row in data[:20]]},
                {"name": "Matrix Rows", "values": [int(row.matrix_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Reviews"), "datatype": "Int"},
        {"value": len([row for row in data if row.design_approved_for_next_phase]), "indicator": "Green", "label": _("Approved"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Blocked"]), "indicator": "Red", "label": _("Blocked"), "datatype": "Int"},
        {"value": data[0].warning_count if data else 0, "indicator": "Orange" if data and int(data[0].warning_count or 0) else "Green", "label": _("Latest Warnings"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_design_exception_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    for field in ["design_review", "status", "severity", "category"]:
        if filters.get(field):
            conditions.append(f"i.{field} = %({field})s")
            params[field] = filters.get(field)
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "NDIS Accounting Design Review Item", "width": 220},
        {"fieldname": "design_review", "label": _("Design Review"), "fieldtype": "Link", "options": "NDIS Accounting Design Review", "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 180},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 280},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 430},
        {"fieldname": "recommendation", "label": _("Recommendation"), "fieldtype": "Small Text", "width": 430},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 180},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Data", "width": 220},
        {"fieldname": "reviewed_on", "label": _("Reviewed On"), "fieldtype": "Datetime", "width": 170},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item, i.design_review, i.status, i.severity, i.category,
            i.check_label, i.detail, i.recommendation, i.source_doctype, i.source_name, i.reviewed_on
        FROM `tabNDIS Accounting Design Review Item` i
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
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Warning"]), "indicator": "Orange", "label": _("Warnings"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Pass"]), "indicator": "Green", "label": _("Pass"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
