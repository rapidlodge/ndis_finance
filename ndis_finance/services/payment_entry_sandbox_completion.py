import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


COMPLETION_ACK = "I_CONFIRM_NDIS_PAYMENT_ENTRY_SANDBOX_CHAIN_REVIEWED"

PHASE_HEALTH_CHECKS = [
    ("Phase 3D", "ndis_finance.setup.phase3d.health_check"),
    ("Phase 3C", "ndis_finance.setup.phase3c.health_check"),
    ("Phase 3B", "ndis_finance.setup.phase3b.health_check"),
    ("Phase 3A", "ndis_finance.setup.phase3a.health_check"),
    ("Phase 2F", "ndis_finance.setup.phase2f.health_check"),
]


def make_gate_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-PE-SANDBOX-GATE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def contains_false_or_none(value):
    if value is False or value is None:
        return True

    if isinstance(value, dict):
        return any(contains_false_or_none(child) for child in value.values())

    if isinstance(value, list):
        return any(contains_false_or_none(child) for child in value)

    return False


def evaluate_health_checks(items):
    for label, method_path in PHASE_HEALTH_CHECKS:
        try:
            result = frappe.get_attr(method_path)()

            if contains_false_or_none(result):
                add_item(
                    items,
                    "Blocker",
                    "Critical",
                    "Regression Health",
                    method_path,
                    f"{label} health check",
                    "Health check returned false/null values.",
                    "Fix the phase health output before moving beyond Payment Entry sandbox.",
                )
            else:
                add_item(items, "Pass", "Low", "Regression Health", method_path, f"{label} health check", "Health check is green.")

        except Exception as exc:
            add_item(
                items,
                "Blocker",
                "Critical",
                "Regression Health",
                method_path,
                f"{label} health check",
                f"Health check failed: {str(exc)}",
                "Fix the failed health check before proceeding.",
            )


def evaluate_config(items):
    sandbox_enabled = int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0)
    production_mode = int(frappe.conf.get("ndis_finance_production_mode") or 0)

    if sandbox_enabled:
        add_item(items, "Pass", "Low", "Site Config", "sandbox_config", "Sandbox posting config", "Sandbox posting config is enabled.")
    else:
        add_item(items, "Warning", "Medium", "Site Config", "sandbox_config", "Sandbox posting config", "Sandbox posting config is not enabled.", "Enable it only in dev/sandbox when testing adapters.")

    if production_mode:
        add_item(items, "Blocker", "Critical", "Site Config", "production_mode", "Production mode", "Production mode flag is enabled.", "Disable production mode before sandbox Payment Entry testing.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "production_mode", "Production mode", "Production mode flag is not enabled.")

    return sandbox_enabled, production_mode


def latest_approved_design_review():
    rows = frappe.get_all(
        "NDIS Accounting Design Review",
        filters={
            "design_approved_for_next_phase": 1,
            "status": ["in", ["Passed", "Needs Review"]],
        },
        fields=["name", "review_id", "status"],
        order_by="reviewed_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def latest_allowed_sandbox_completion_gate():
    rows = frappe.get_all(
        "NDIS Accounting Sandbox Completion Gate",
        filters={
            "sandbox_completion_allowed": 1,
            "status": ["in", ["Passed", "Needs Review"]],
        },
        fields=["name", "gate_id", "completion_score"],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def evaluate_design_and_accounting_gate(items):
    design = latest_approved_design_review()
    accounting_gate = latest_allowed_sandbox_completion_gate()

    if design:
        add_item(items, "Pass", "Low", "Design Evidence", "approved_design_review", "Approved Phase 3A design review", "Approved accounting design review found.", None, "NDIS Accounting Design Review", design.name)
    else:
        add_item(items, "Blocker", "Critical", "Design Evidence", "approved_design_review", "Approved Phase 3A design review", "No approved Phase 3A design review found.", "Run Phase 3A design review with acknowledgement.")

    if accounting_gate:
        add_item(items, "Pass", "Low", "Sandbox Evidence", "accounting_sandbox_completion_gate", "Accounting sandbox completion gate", f"Allowed accounting sandbox completion gate found with score {accounting_gate.completion_score}.", None, "NDIS Accounting Sandbox Completion Gate", accounting_gate.name)
    else:
        add_item(items, "Blocker", "Critical", "Sandbox Evidence", "accounting_sandbox_completion_gate", "Accounting sandbox completion gate", "No allowed Phase 2F accounting sandbox completion gate found.", "Run Phase 2F completion gate with acknowledgement.")

    return design, accounting_gate


def evaluate_mapping_and_preview(items):
    mapping_count = frappe.db.count("NDIS Payment Entry Mapping Rule")
    preview_count = frappe.db.count("NDIS Payment Entry Allocation Preview")
    allocatable_preview_count = frappe.db.count(
        "NDIS Payment Entry Allocation Preview",
        {"allocatable_line_count": [">", 0], "status": ["!=", "Cancelled"]},
    )

    if mapping_count:
        add_item(items, "Pass", "Low", "Payment Entry Mapping", "mapping_rules", "Payment Entry mapping rules", f"{mapping_count} mapping rule(s) found.")
    else:
        add_item(items, "Blocker", "Critical", "Payment Entry Mapping", "mapping_rules", "Payment Entry mapping rules", "No Payment Entry mapping rules found.", "Install Phase 3B mapping rules.")

    if preview_count:
        add_item(items, "Pass", "Low", "Payment Entry Preview", "allocation_previews", "Allocation previews", f"{preview_count} allocation preview(s) found.")
    else:
        add_item(items, "Warning", "Medium", "Payment Entry Preview", "allocation_previews", "Allocation previews", "No allocation previews found.", "Run Phase 3B allocation preview when remittance data is available.")

    if allocatable_preview_count:
        add_item(items, "Pass", "Low", "Payment Entry Preview", "allocatable_previews", "Allocatable previews", f"{allocatable_preview_count} preview(s) have allocatable lines.")
    else:
        add_item(
            items,
            "Warning",
            "High",
            "Payment Entry Preview",
            "allocatable_previews",
            "Allocatable invoice-backed preview lines",
            "No allocation preview currently has allocatable invoice-backed lines.",
            "Expected on this site because no Sales Invoice rows exist. Complete real PE smoke test when legitimate Sales Invoice data exists.",
        )

    return mapping_count, preview_count, allocatable_preview_count


def evaluate_sandbox_pe_runs(items):
    run_count = frappe.db.count("NDIS Sandbox Payment Entry Run")
    created_draft_run_count = frappe.db.count("NDIS Sandbox Payment Entry Run", {"status": "Created Draft Payment Entry"})

    if run_count:
        add_item(items, "Pass", "Low", "Sandbox PE Adapter", "sandbox_pe_runs", "Sandbox PE run evidence", f"{run_count} sandbox Payment Entry run(s) found.")
    else:
        add_item(items, "Info", "Low", "Sandbox PE Adapter", "sandbox_pe_runs", "Sandbox PE run evidence", "No sandbox Payment Entry run exists yet.", "This is acceptable if no invoice-backed allocatable preview is available.")

    if created_draft_run_count:
        add_item(items, "Pass", "Low", "Sandbox PE Adapter", "created_draft_pe_runs", "Invoice-backed draft PE smoke test", f"{created_draft_run_count} run(s) created draft sandbox Payment Entry.")
        invoice_backed_smoke_test_pending = 0
    else:
        add_item(items, "Warning", "High", "Sandbox PE Adapter", "created_draft_pe_runs", "Invoice-backed draft PE smoke test", "No draft sandbox Payment Entry has been created yet.", "Expected on current site because there is no Sales Invoice data. Complete this smoke test once legitimate invoice-backed data exists.")
        invoice_backed_smoke_test_pending = 1

    return run_count, created_draft_run_count, invoice_backed_smoke_test_pending


def evaluate_cleanup(items):
    cleanup_run_count = frappe.db.count("NDIS Sandbox Payment Entry Cleanup Run")

    if cleanup_run_count:
        add_item(items, "Pass", "Low", "Cleanup Evidence", "cleanup_runs", "Sandbox PE cleanup run evidence", f"{cleanup_run_count} cleanup run(s) found.")
    else:
        add_item(items, "Warning", "Medium", "Cleanup Evidence", "cleanup_runs", "Sandbox PE cleanup run evidence", "No cleanup run found.", "Run Phase 3D cleanup preview.")

    return cleanup_run_count


def get_sandbox_pe_gl_count():
    pe_names = set()

    for row in frappe.get_all("Payment Entry", filters={"custom_ndis_sandbox_payment_entry_draft_only": 1}, fields=["name"], limit=10000):
        pe_names.add(row.name)

    for row in frappe.get_all("NDIS Sandbox Payment Entry Cleanup Line", fields=["payment_entry"], limit=10000):
        if row.payment_entry:
            pe_names.add(row.payment_entry)

    for row in frappe.get_all("NDIS Sandbox Payment Entry Run", fields=["payment_entry"], limit=10000):
        if row.payment_entry:
            pe_names.add(row.payment_entry)

    if not pe_names or not frappe.db.exists("DocType", "GL Entry"):
        return 0

    return frappe.db.count("GL Entry", {"voucher_type": "Payment Entry", "voucher_no": ["in", list(pe_names)]})


def evaluate_hygiene(items, stale_age_days=7):
    draft_count = frappe.db.count("Payment Entry", {"custom_ndis_sandbox_payment_entry_draft_only": 1, "docstatus": 0})
    submitted_count = frappe.db.count("Payment Entry", {"custom_ndis_sandbox_payment_entry_draft_only": 1, "docstatus": 1})
    stale_count = frappe.db.sql(
        """
        SELECT COUNT(*) AS count
        FROM `tabPayment Entry`
        WHERE custom_ndis_sandbox_payment_entry_draft_only = 1
        AND docstatus = 0
        AND DATE(creation) <= DATE_SUB(CURDATE(), INTERVAL %(stale_age_days)s DAY)
        """,
        {"stale_age_days": int(stale_age_days or 7)},
        as_dict=True,
    )[0].count
    gl_count = get_sandbox_pe_gl_count()

    if submitted_count:
        add_item(items, "Blocker", "Critical", "Sandbox PE Hygiene", "submitted_sandbox_pe", "Submitted sandbox Payment Entries", f"{submitted_count} submitted sandbox PE(s) found.", "Submitted sandbox Payment Entries must never exist.")
    else:
        add_item(items, "Pass", "Low", "Sandbox PE Hygiene", "submitted_sandbox_pe", "Submitted sandbox Payment Entries", "No submitted sandbox Payment Entries found.")

    if gl_count:
        add_item(items, "Blocker", "Critical", "Sandbox PE Hygiene", "sandbox_pe_gl_entries", "GL linked to sandbox Payment Entries", f"{gl_count} GL Entry record(s) linked to sandbox Payment Entry evidence.", "Investigate immediately. Sandbox Payment Entries must not create GL.")
    else:
        add_item(items, "Pass", "Low", "Sandbox PE Hygiene", "sandbox_pe_gl_entries", "GL linked to sandbox Payment Entries", "No GL Entries linked to sandbox Payment Entry evidence found.")

    if stale_count:
        add_item(items, "Warning", "High", "Sandbox PE Hygiene", "stale_sandbox_pe", "Stale draft sandbox Payment Entries", f"{stale_count} stale draft sandbox PE(s) found.", "Run Phase 3D cleanup.")
    else:
        add_item(items, "Pass", "Low", "Sandbox PE Hygiene", "stale_sandbox_pe", "Stale draft sandbox Payment Entries", "No stale draft sandbox Payment Entries found.")

    if draft_count:
        add_item(items, "Warning", "Medium", "Sandbox PE Hygiene", "draft_sandbox_pe", "Remaining draft sandbox Payment Entries", f"{draft_count} draft sandbox PE(s) remain.", "Acceptable for active testing only. Clean up old drafts.")
    else:
        add_item(items, "Pass", "Low", "Sandbox PE Hygiene", "draft_sandbox_pe", "Remaining draft sandbox Payment Entries", "No remaining draft sandbox Payment Entries found.")

    return draft_count, submitted_count, gl_count, stale_count


def evaluate_movement_guardrails(items):
    counts = {
        "Submitted Payment Entry": frappe.db.count("Payment Entry", {"creation": [">=", today()], "docstatus": 1}),
        "Submitted Journal Entry": frappe.db.count("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
        "GL Entry": frappe.db.count("GL Entry", {"creation": [">=", today()]}) if frappe.db.exists("DocType", "GL Entry") else 0,
        "Sales Invoice": frappe.db.count("Sales Invoice", {"creation": [">=", today()]}) if frappe.db.exists("DocType", "Sales Invoice") else 0,
        "Purchase Invoice": frappe.db.count("Purchase Invoice", {"creation": [">=", today()]}) if frappe.db.exists("DocType", "Purchase Invoice") else 0,
    }
    total = sum(int(value or 0) for value in counts.values())

    if total:
        add_item(items, "Warning", "Medium", "Movement Guardrail", "movement_counts_today", "Strict movement counts today", "Today counts: " + ", ".join([f"{key}={value}" for key, value in counts.items()]), "Confirm these are unrelated to Phase 3E because Phase 3E must not create accounting movement.")
    else:
        add_item(items, "Pass", "Low", "Movement Guardrail", "movement_counts_today", "Strict movement counts today", "No submitted PE, submitted JE, GL Entry, Sales Invoice or Purchase Invoice created today.")

    return counts


def summarise_items(items):
    return {
        "blocker_count": len([item for item in items if item["status"] == "Blocker"]),
        "warning_count": len([item for item in items if item["status"] == "Warning"]),
        "pass_count": len([item for item in items if item["status"] == "Pass"]),
        "info_count": len([item for item in items if item["status"] == "Info"]),
        "item_count": len(items),
    }


def calculate_score(blockers, warnings):
    score = 100 - int(blockers or 0) * 25 - int(warnings or 0) * 5
    return max(0, round(score, 2))


def completion_status(score, blockers, smoke_pending):
    if blockers:
        return "Blocked"
    if smoke_pending:
        return "Ready With Pending Smoke Test"
    if score >= 90:
        return "Structurally Ready"
    return "Needs Review"


@frappe.whitelist()
def run_payment_entry_sandbox_completion_gate(gate_type="Payment Entry Sandbox Completion", stale_age_days=7, acknowledgement=None, dry_run=0, notes=None):
    assert_action("run_payment_entry_sandbox_completion_gate")

    items = []
    sandbox_config_enabled, production_mode_detected = evaluate_config(items)
    evaluate_health_checks(items)
    design_review, accounting_gate = evaluate_design_and_accounting_gate(items)
    mapping_count, preview_count, allocatable_preview_count = evaluate_mapping_and_preview(items)
    sandbox_pe_run_count, created_draft_pe_run_count, invoice_backed_smoke_test_pending = evaluate_sandbox_pe_runs(items)
    cleanup_run_count = evaluate_cleanup(items)
    draft_sandbox_pe_count, submitted_sandbox_pe_count, sandbox_pe_gl_entry_count, stale_draft_sandbox_pe_count = evaluate_hygiene(items, stale_age_days=stale_age_days)
    movement_counts = evaluate_movement_guardrails(items)
    ack_ok = acknowledgement == COMPLETION_ACK

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "completion_ack", "Payment Entry sandbox completion acknowledgement", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "completion_ack", "Payment Entry sandbox completion acknowledgement", f"Required acknowledgement not supplied. Required: {COMPLETION_ACK}", "Provide exact acknowledgement to allow structural completion.")

    summary = summarise_items(items)
    score = calculate_score(summary["blocker_count"], summary["warning_count"])
    final_completion_status = completion_status(score, summary["blocker_count"], invoice_backed_smoke_test_pending)
    structural_ready_allowed = int(summary["blocker_count"] == 0 and ack_ok)

    if summary["blocker_count"]:
        status = "Blocked"
    elif summary["warning_count"] or not ack_ok:
        status = "Needs Review"
    else:
        status = "Passed"

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "gate_type": gate_type,
        "status": status,
        "sandbox_structural_ready_allowed": structural_ready_allowed,
        "invoice_backed_smoke_test_pending": invoice_backed_smoke_test_pending,
        "required_acknowledgement": COMPLETION_ACK,
        "acknowledgement_ok": ack_ok,
        "summary": summary,
        "completion_score": score,
        "completion_status": final_completion_status,
        "evidence_counts": {
            "approved_design_review_count": 1 if design_review else 0,
            "allocation_preview_count": preview_count,
            "allocatable_preview_count": allocatable_preview_count,
            "sandbox_pe_run_count": sandbox_pe_run_count,
            "created_draft_pe_run_count": created_draft_pe_run_count,
            "cleanup_run_count": cleanup_run_count,
        },
        "hygiene_counts": {
            "draft_sandbox_pe_count": draft_sandbox_pe_count,
            "submitted_sandbox_pe_count": submitted_sandbox_pe_count,
            "sandbox_pe_gl_entry_count": sandbox_pe_gl_entry_count,
            "stale_draft_sandbox_pe_count": stale_draft_sandbox_pe_count,
        },
        "movement_counts": movement_counts,
        "items": items,
        "note": "Payment Entry sandbox completion gate only. No Payment Entry, Journal Entry, GL Entry, Sales Invoice, Purchase Invoice, payroll posting, STP, ABA, email, Xero export, bank allocation, or payment movement created.",
    }

    if int(dry_run or 0):
        return result

    doc = frappe.new_doc("NDIS Payment Entry Sandbox Completion Gate")
    doc.gate_id = make_gate_id()
    doc.gate_type = gate_type
    doc.status = status
    doc.sandbox_structural_ready_allowed = structural_ready_allowed
    doc.invoice_backed_smoke_test_pending = invoice_backed_smoke_test_pending
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = sandbox_config_enabled
    doc.production_mode_detected = production_mode_detected
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.blocker_count = summary["blocker_count"]
    doc.warning_count = summary["warning_count"]
    doc.pass_count = summary["pass_count"]
    doc.info_count = summary["info_count"]
    doc.item_count = summary["item_count"]
    doc.completion_score = score
    doc.completion_status = final_completion_status
    doc.approved_design_review_count = 1 if design_review else 0
    doc.allocation_preview_count = preview_count
    doc.allocatable_preview_count = allocatable_preview_count
    doc.sandbox_pe_run_count = sandbox_pe_run_count
    doc.created_draft_pe_run_count = created_draft_pe_run_count
    doc.cleanup_run_count = cleanup_run_count
    doc.draft_sandbox_pe_count = draft_sandbox_pe_count
    doc.submitted_sandbox_pe_count = submitted_sandbox_pe_count
    doc.sandbox_pe_gl_entry_count = sandbox_pe_gl_entry_count
    doc.stale_draft_sandbox_pe_count = stale_draft_sandbox_pe_count
    doc.submitted_payment_entry_count_today = movement_counts.get("Submitted Payment Entry", 0)
    doc.submitted_journal_entry_count_today = movement_counts.get("Submitted Journal Entry", 0)
    doc.gl_entry_count_today = movement_counts.get("GL Entry", 0)
    doc.sales_invoice_count_today = movement_counts.get("Sales Invoice", 0)
    doc.purchase_invoice_count_today = movement_counts.get("Purchase Invoice", 0)
    doc.required_acknowledgement = COMPLETION_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    for item in items:
        row = frappe.new_doc("NDIS Payment Entry Sandbox Completion Gate Item")
        row.completion_gate = doc.name
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
    result["completion_gate"] = doc.name
    result["gate_id"] = doc.gate_id
    return result


@frappe.whitelist()
def cancel_payment_entry_sandbox_completion_gate(completion_gate, reason=None):
    assert_action("cancel_payment_entry_sandbox_completion_gate")

    if not frappe.db.exists("NDIS Payment Entry Sandbox Completion Gate", completion_gate):
        frappe.throw(_("Payment Entry Sandbox Completion Gate not found: {0}").format(completion_gate))

    frappe.db.set_value(
        "NDIS Payment Entry Sandbox Completion Gate",
        completion_gate,
        {
            "status": "Cancelled",
            "sandbox_structural_ready_allowed": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "warning_log": reason or "Payment Entry sandbox completion gate cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        """
        UPDATE `tabNDIS Payment Entry Sandbox Completion Gate Item`
        SET status = 'Cancelled'
        WHERE completion_gate = %(completion_gate)s
        """,
        {"completion_gate": completion_gate},
    )
    frappe.db.commit()
    return {"completion_gate": completion_gate, "status": "Cancelled", "note": "Completion gate cancelled only. No accounting/payment records were changed."}


@frappe.whitelist()
def quick_payment_entry_sandbox_completion_summary(limit=20):
    gates = frappe.get_all(
        "NDIS Payment Entry Sandbox Completion Gate",
        fields=[
            "name",
            "gate_id",
            "status",
            "sandbox_structural_ready_allowed",
            "invoice_backed_smoke_test_pending",
            "completion_score",
            "completion_status",
            "blocker_count",
            "warning_count",
            "draft_sandbox_pe_count",
            "submitted_sandbox_pe_count",
            "sandbox_pe_gl_entry_count",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        "NDIS Payment Entry Sandbox Completion Gate Item",
        fields=["name", "completion_gate", "status", "severity", "category", "check_label", "detail", "recommendation", "source_doctype", "source_name"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {"gates": gates, "items": items, "required_acknowledgement": COMPLETION_ACK, "note": "Payment Entry sandbox completion summary only. No accounting/payment movement created."}


def execute_completion_gate_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("status"):
        conditions.append("g.status = %(status)s")
        params["status"] = filters.get("status")

    if filters.get("completion_status"):
        conditions.append("g.completion_status = %(completion_status)s")
        params["completion_status"] = filters.get("completion_status")

    smoke_pending = filters.get("invoice_backed_smoke_test_pending")
    if smoke_pending not in [None, ""]:
        conditions.append("g.invoice_backed_smoke_test_pending = %(smoke_pending)s")
        params["smoke_pending"] = int(smoke_pending)

    if filters.get("from_date"):
        conditions.append("DATE(g.checked_on) >= %(from_date)s")
        params["from_date"] = filters.get("from_date")

    if filters.get("to_date"):
        conditions.append("DATE(g.checked_on) <= %(to_date)s")
        params["to_date"] = filters.get("to_date")

    columns = [
        {"fieldname": "completion_gate", "label": _("Completion Gate"), "fieldtype": "Link", "options": "NDIS Payment Entry Sandbox Completion Gate", "width": 220},
        {"fieldname": "gate_id", "label": _("Gate ID"), "fieldtype": "Data", "width": 310},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "sandbox_structural_ready_allowed", "label": _("Structurally Ready"), "fieldtype": "Check", "width": 120},
        {"fieldname": "invoice_backed_smoke_test_pending", "label": _("Smoke Pending"), "fieldtype": "Check", "width": 120},
        {"fieldname": "completion_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "completion_status", "label": _("Completion Status"), "fieldtype": "Data", "width": 220},
        {"fieldname": "blocker_count", "label": _("Blockers"), "fieldtype": "Int", "width": 90},
        {"fieldname": "warning_count", "label": _("Warnings"), "fieldtype": "Int", "width": 90},
        {"fieldname": "created_draft_pe_run_count", "label": _("Draft PE Runs"), "fieldtype": "Int", "width": 120},
        {"fieldname": "draft_sandbox_pe_count", "label": _("Draft Sandbox PEs"), "fieldtype": "Int", "width": 130},
        {"fieldname": "submitted_sandbox_pe_count", "label": _("Submitted Sandbox PEs"), "fieldtype": "Int", "width": 160},
        {"fieldname": "sandbox_pe_gl_entry_count", "label": _("Sandbox PE GL"), "fieldtype": "Int", "width": 120},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "checked_by", "label": _("Checked By"), "fieldtype": "Link", "options": "User", "width": 160},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            g.name AS completion_gate,
            g.gate_id,
            g.status,
            g.sandbox_structural_ready_allowed,
            g.invoice_backed_smoke_test_pending,
            g.completion_score,
            g.completion_status,
            g.blocker_count,
            g.warning_count,
            g.created_draft_pe_run_count,
            g.draft_sandbox_pe_count,
            g.submitted_sandbox_pe_count,
            g.sandbox_pe_gl_entry_count,
            g.checked_on,
            g.checked_by
        FROM `tabNDIS Payment Entry Sandbox Completion Gate` g
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
                {"name": "Score", "values": [flt(row.completion_score) for row in data[:20]]},
                {"name": "Blockers", "values": [int(row.blocker_count or 0) for row in data[:20]]},
                {"name": "Warnings", "values": [int(row.warning_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Gates"), "datatype": "Int"},
        {"value": len([row for row in data if row.sandbox_structural_ready_allowed]), "indicator": "Green", "label": _("Structurally Ready"), "datatype": "Int"},
        {"value": len([row for row in data if row.invoice_backed_smoke_test_pending]), "indicator": "Orange", "label": _("Smoke Pending"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Blocked"]), "indicator": "Red", "label": _("Blocked"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_completion_exception_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    for key, column in [
        ("completion_gate", "i.completion_gate"),
        ("status", "i.status"),
        ("severity", "i.severity"),
        ("category", "i.category"),
    ]:
        if filters.get(key):
            conditions.append(f"{column} = %({key})s")
            params[key] = filters.get(key)

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "NDIS Payment Entry Sandbox Completion Gate Item", "width": 220},
        {"fieldname": "completion_gate", "label": _("Completion Gate"), "fieldtype": "Link", "options": "NDIS Payment Entry Sandbox Completion Gate", "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 190},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 300},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 430},
        {"fieldname": "recommendation", "label": _("Recommendation"), "fieldtype": "Small Text", "width": 430},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 180},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Data", "width": 220},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item,
            i.completion_gate,
            i.status,
            i.severity,
            i.category,
            i.check_label,
            i.detail,
            i.recommendation,
            i.source_doctype,
            i.source_name,
            i.checked_on
        FROM `tabNDIS Payment Entry Sandbox Completion Gate Item` i
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
