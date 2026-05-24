import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


FREEZE_ACK = "I_CONFIRM_FREEZE_PAYMENT_ENTRY_SANDBOX_READINESS"

FREEZE_DOCTYPE = "NDIS PE Sandbox Readiness Freeze"
FREEZE_ITEM_DOCTYPE = "NDIS PE Sandbox Readiness Freeze Item"

PHASE_HEALTH_CHECKS = [
    ("Phase 4C", "ndis_finance.setup.phase4c.health_check"),
    ("Phase 4B", "ndis_finance.setup.phase4b.health_check"),
    ("Phase 4A", "ndis_finance.setup.phase4a.health_check"),
    ("Phase 3E", "ndis_finance.setup.phase3e.health_check"),
    ("Phase 3D", "ndis_finance.setup.phase3d.health_check"),
    ("Phase 3C", "ndis_finance.setup.phase3c.health_check"),
    ("Phase 3B", "ndis_finance.setup.phase3b.health_check"),
    ("Phase 3A", "ndis_finance.setup.phase3a.health_check"),
    ("Phase 2F", "ndis_finance.setup.phase2f.health_check"),
]


def make_freeze_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-PE-SANDBOX-FREEZE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


def currency():
    return frappe.defaults.get_global_default("currency") or "AUD"


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
    rows = frappe.get_all(
        doctype,
        filters=filters or {},
        fields=fields or ["name"],
        order_by=order_by,
        limit=1,
    )
    return rows[0] if rows else None


def evaluate_config(items):
    sandbox_enabled = int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0)
    production_mode = int(frappe.conf.get("ndis_finance_production_mode") or 0)

    if sandbox_enabled:
        add_item(items, "Pass", "Low", "Site Config", "sandbox_enabled", "Sandbox config enabled", "Sandbox posting config is enabled.")
    else:
        add_item(items, "Warning", "Medium", "Site Config", "sandbox_enabled", "Sandbox config enabled", "Sandbox posting config is not enabled.")

    if production_mode:
        add_item(items, "Blocker", "Critical", "Site Config", "production_mode", "Production mode", "Production mode is enabled.", "Disable production mode before freezing sandbox readiness.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "production_mode", "Production mode", "Production mode is disabled.")

    return sandbox_enabled, production_mode


def evaluate_health(items):
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
                    "Fix the phase health check before readiness freeze.",
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
                "Fix the failed health check before readiness freeze.",
            )


def evaluate_evidence(items):
    approved_design = latest_doc(
        "NDIS Accounting Design Review",
        {"design_approved_for_next_phase": 1, "status": ["in", ["Passed", "Needs Review"]]},
        ["name", "review_id"],
        "reviewed_on desc, creation desc",
    )
    allocation_preview_count = count_dt("NDIS Payment Entry Allocation Preview")
    draft_pe_run_count = count_dt("NDIS Sandbox Payment Entry Run", {"status": "Created Draft Payment Entry"})
    smoke_count = count_dt("NDIS Invoice Backed PE Smoke Run", {"status": "Completed"})
    cleanup_count = count_dt("NDIS Sandbox Accounting Cleanup Pack", {"status": "Cleaned"})
    cleared_gate = latest_doc(
        "NDIS Payment Entry Sandbox Completion Gate",
        {
            "sandbox_structural_ready_allowed": 1,
            "invoice_backed_smoke_test_pending": 0,
            "blocker_count": 0,
            "status": ["in", ["Passed", "Needs Review"]],
        },
        ["name", "gate_id", "completion_score", "completion_status"],
        "checked_on desc, creation desc",
    )

    if approved_design:
        add_item(items, "Pass", "Low", "Evidence", "approved_design", "Approved design review", "Approved Phase 3A accounting design review found.", None, "NDIS Accounting Design Review", approved_design.name)
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "approved_design", "Approved design review", "No approved Phase 3A design review found.", "Run Phase 3A review with acknowledgement.")

    if allocation_preview_count:
        add_item(items, "Pass", "Low", "Evidence", "allocation_preview", "Allocation preview layer", f"{allocation_preview_count} allocation preview record(s) found.")
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "allocation_preview", "Allocation preview layer", "No Payment Entry allocation preview found.")

    if draft_pe_run_count:
        add_item(items, "Pass", "Low", "Evidence", "draft_pe_adapter", "Draft PE adapter proven", f"{draft_pe_run_count} sandbox draft PE run(s) found.")
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "draft_pe_adapter", "Draft PE adapter proven", "No completed draft Payment Entry sandbox run found.")

    latest_smoke = latest_doc("NDIS Invoice Backed PE Smoke Run", {"status": "Completed"}, ["name", "run_id", "payment_entry"], "created_on desc, creation desc")
    if smoke_count and latest_smoke:
        add_item(items, "Pass", "Low", "Evidence", "invoice_backed_smoke", "Invoice-backed PE smoke proven", f"{smoke_count} completed invoice-backed PE smoke run(s) found.", None, "NDIS Invoice Backed PE Smoke Run", latest_smoke.name)
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "invoice_backed_smoke", "Invoice-backed PE smoke proven", "No completed Phase 4B invoice-backed PE smoke run found.")

    latest_cleanup = latest_doc("NDIS Sandbox Accounting Cleanup Pack", {"status": "Cleaned"}, ["name", "pack_id"], "created_on desc, creation desc")
    if cleanup_count and latest_cleanup:
        add_item(items, "Pass", "Low", "Evidence", "cleanup_pack", "Cleanup pack proven", f"{cleanup_count} cleaned sandbox accounting cleanup pack(s) found.", None, "NDIS Sandbox Accounting Cleanup Pack", latest_cleanup.name)
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "cleanup_pack", "Cleanup pack proven", "No cleaned Phase 4C cleanup pack found.")

    if cleared_gate:
        add_item(items, "Pass", "Low", "Evidence", "phase3e_cleared", "Phase 3E completion gate cleared", f"Latest cleared gate: {cleared_gate.gate_id}.", None, "NDIS Payment Entry Sandbox Completion Gate", cleared_gate.name)
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase3e_cleared", "Phase 3E completion gate cleared", "No Phase 3E gate found with invoice_backed_smoke_test_pending = 0 and blocker_count = 0.", "Rerun Phase 3E after Phase 4C cleanup.")

    return {
        "design_review_count": 1 if approved_design else 0,
        "allocation_preview_count": allocation_preview_count,
        "draft_pe_run_count": draft_pe_run_count,
        "invoice_backed_smoke_count": smoke_count,
        "cleanup_pack_count": cleanup_count,
        "phase3e_cleared_gate_count": 1 if cleared_gate else 0,
    }


def gl_count(voucher_type=None):
    if not frappe.db.exists("DocType", "GL Entry"):
        return 0
    filters = {}
    if voucher_type:
        filters["voucher_type"] = voucher_type
    return frappe.db.count("GL Entry", filters)


def sandbox_si_gl_count_and_net():
    if not frappe.db.exists("DocType", "GL Entry"):
        return 0, 0
    result = frappe.db.sql(
        """
        SELECT COUNT(*) AS gl_count, COALESCE(SUM(gle.debit - gle.credit), 0) AS gl_net
        FROM `tabGL Entry` gle
        WHERE gle.voucher_type = 'Sales Invoice'
        AND gle.voucher_no IN (
            SELECT si.name FROM `tabSales Invoice` si
            WHERE si.custom_ndis_sandbox_test_invoice = 1
        )
        """,
        as_dict=True,
    )
    row = result[0] if result else frappe._dict({"gl_count": 0, "gl_net": 0})
    return int(row.gl_count or 0), flt(row.gl_net or 0)


def unrelated_gl_today():
    if not frappe.db.exists("DocType", "GL Entry"):
        return 0
    return int(
        frappe.db.sql(
            """
            SELECT COUNT(*) AS count
            FROM `tabGL Entry` gle
            WHERE DATE(gle.creation) = CURDATE()
            AND NOT (
                gle.voucher_type = 'Sales Invoice'
                AND gle.voucher_no IN (
                    SELECT si.name FROM `tabSales Invoice` si
                    WHERE si.custom_ndis_sandbox_test_invoice = 1
                )
            )
            """,
            as_dict=True,
        )[0].count
        or 0
    )


def evaluate_hygiene(items):
    draft_pe = count_dt("Payment Entry", {"custom_ndis_sandbox_payment_entry_draft_only": 1, "docstatus": 0})
    submitted_pe = count_dt("Payment Entry", {"custom_ndis_sandbox_payment_entry_draft_only": 1, "docstatus": 1})
    pe_gl = gl_count("Payment Entry")
    submitted_si = count_dt("Sales Invoice", {"custom_ndis_sandbox_test_invoice": 1, "docstatus": 1})
    cancelled_si = count_dt("Sales Invoice", {"custom_ndis_sandbox_test_invoice": 1, "docstatus": 2})
    draft_si = count_dt("Sales Invoice", {"custom_ndis_sandbox_test_invoice": 1, "docstatus": 0})
    si_gl_count, si_gl_net = sandbox_si_gl_count_and_net()

    if draft_pe:
        add_item(items, "Blocker", "Critical", "Sandbox Hygiene", "draft_sandbox_pe", "Draft sandbox Payment Entries", f"{draft_pe} draft sandbox Payment Entry record(s) remain.", "Run Phase 4C cleanup pack.")
    else:
        add_item(items, "Pass", "Low", "Sandbox Hygiene", "draft_sandbox_pe", "Draft sandbox Payment Entries", "No draft sandbox Payment Entries remain.")

    if submitted_pe:
        add_item(items, "Blocker", "Critical", "Sandbox Hygiene", "submitted_sandbox_pe", "Submitted sandbox Payment Entries", f"{submitted_pe} submitted sandbox Payment Entry record(s) found.", "Investigate immediately. Sandbox PE must never submit.")
    else:
        add_item(items, "Pass", "Low", "Sandbox Hygiene", "submitted_sandbox_pe", "Submitted sandbox Payment Entries", "No submitted sandbox Payment Entries found.")

    if pe_gl:
        add_item(items, "Blocker", "Critical", "Sandbox Hygiene", "payment_entry_gl", "Payment Entry GL", f"{pe_gl} GL Entry record(s) exist for Payment Entry.", "Investigate immediately. Sandbox PE must create no GL.")
    else:
        add_item(items, "Pass", "Low", "Sandbox Hygiene", "payment_entry_gl", "Payment Entry GL", "No Payment Entry GL exists.")

    if submitted_si:
        add_item(items, "Blocker", "Critical", "Sandbox Hygiene", "submitted_sandbox_si", "Submitted sandbox Sales Invoices", f"{submitted_si} submitted sandbox SI record(s) remain.", "Cancel submitted sandbox SI through Phase 4C cleanup.")
    else:
        add_item(items, "Pass", "Low", "Sandbox Hygiene", "submitted_sandbox_si", "Submitted sandbox Sales Invoices", "No submitted sandbox Sales Invoice remains.")

    if cancelled_si:
        add_item(items, "Pass", "Low", "Sandbox Hygiene", "cancelled_sandbox_si", "Cancelled sandbox Sales Invoice evidence", f"{cancelled_si} cancelled sandbox SI record(s) found.")
    else:
        add_item(items, "Warning", "Medium", "Sandbox Hygiene", "cancelled_sandbox_si", "Cancelled sandbox Sales Invoice evidence", "No cancelled sandbox SI evidence found.", "Confirm Phase 4C cancelled the submitted sandbox SI.")

    if draft_si:
        add_item(items, "Info", "Low", "Sandbox Hygiene", "draft_sandbox_si", "Draft sandbox Sales Invoice", f"{draft_si} draft sandbox SI record(s) remain. This is acceptable because draft SI created no GL.")
    else:
        add_item(items, "Pass", "Low", "Sandbox Hygiene", "draft_sandbox_si", "Draft sandbox Sales Invoice", "No draft sandbox SI remains.")

    if abs(flt(si_gl_net)) <= 0.0001:
        add_item(items, "Pass", "Low", "Sandbox Hygiene", "sandbox_si_gl_net", "Sandbox SI GL net", f"Sandbox SI GL net is {flt(si_gl_net):.2f}.")
    else:
        add_item(items, "Blocker", "Critical", "Sandbox Hygiene", "sandbox_si_gl_net", "Sandbox SI GL net", f"Sandbox SI GL net is {flt(si_gl_net):.2f}; expected 0.00 after cancellation.", "Investigate sandbox Sales Invoice GL reversal.")

    return {
        "draft_sandbox_pe_count": draft_pe,
        "submitted_sandbox_pe_count": submitted_pe,
        "payment_entry_gl_count": pe_gl,
        "submitted_sandbox_si_count": submitted_si,
        "cancelled_sandbox_si_count": cancelled_si,
        "draft_sandbox_si_count": draft_si,
        "sandbox_si_gl_count": si_gl_count,
        "sandbox_si_gl_net": flt(si_gl_net),
    }


def evaluate_guardrails(items):
    submitted_pe_today = count_dt("Payment Entry", {"creation": [">=", today()], "docstatus": 1})
    pe_gl_today = count_dt("GL Entry", {"creation": [">=", today()], "voucher_type": "Payment Entry"}) if frappe.db.exists("DocType", "GL Entry") else 0
    submitted_je_today = count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}) if frappe.db.exists("DocType", "Journal Entry") else 0
    purchase_invoice_today = count_dt("Purchase Invoice", {"creation": [">=", today()]}) if frappe.db.exists("DocType", "Purchase Invoice") else 0
    unrelated_gl = unrelated_gl_today()

    if submitted_pe_today:
        add_item(items, "Blocker", "Critical", "Strict Guardrail", "submitted_pe_today", "Submitted Payment Entries today", f"{submitted_pe_today} submitted Payment Entry record(s) today.")
    else:
        add_item(items, "Pass", "Low", "Strict Guardrail", "submitted_pe_today", "Submitted Payment Entries today", "No submitted Payment Entry today.")

    if pe_gl_today:
        add_item(items, "Blocker", "Critical", "Strict Guardrail", "pe_gl_today", "Payment Entry GL today", f"{pe_gl_today} Payment Entry GL record(s) today.")
    else:
        add_item(items, "Pass", "Low", "Strict Guardrail", "pe_gl_today", "Payment Entry GL today", "No Payment Entry GL today.")

    if submitted_je_today:
        add_item(items, "Blocker", "Critical", "Strict Guardrail", "submitted_je_today", "Submitted Journal Entries today", f"{submitted_je_today} submitted Journal Entry record(s) today.")
    else:
        add_item(items, "Pass", "Low", "Strict Guardrail", "submitted_je_today", "Submitted Journal Entries today", "No submitted Journal Entry today.")

    if purchase_invoice_today:
        add_item(items, "Blocker", "Critical", "Strict Guardrail", "purchase_invoice_today", "Purchase Invoices today", f"{purchase_invoice_today} Purchase Invoice record(s) today.")
    else:
        add_item(items, "Pass", "Low", "Strict Guardrail", "purchase_invoice_today", "Purchase Invoices today", "No Purchase Invoice today.")

    if unrelated_gl:
        add_item(items, "Warning", "Medium", "Strict Guardrail", "unrelated_gl_today", "Unrelated GL today", f"{unrelated_gl} GL Entry record(s) today not linked to tagged sandbox Sales Invoice.", "Confirm these are unrelated to Phase 4D.")
    else:
        add_item(items, "Pass", "Low", "Strict Guardrail", "unrelated_gl_today", "Unrelated GL today", "No unrelated GL Entry today outside tagged sandbox Sales Invoice evidence.")

    return {
        "submitted_payment_entry_count_today": submitted_pe_today,
        "payment_entry_gl_count_today": pe_gl_today,
        "submitted_journal_entry_count_today": submitted_je_today,
        "purchase_invoice_count_today": purchase_invoice_today,
        "unrelated_gl_count_today": unrelated_gl,
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
    score = 100 - int(blockers or 0) * 25 - int(warnings or 0) * 5
    return max(0, round(score, 2))


def readiness_status(score, blockers, warnings):
    if blockers:
        return "Blocked"
    if warnings:
        return "Ready With Warnings"
    if score >= 95:
        return "Ready For Next Design Phase"
    return "Needs Review"


@frappe.whitelist()
def run_pe_sandbox_readiness_freeze(freeze_type="Payment Entry Sandbox Readiness", acknowledgement=None, dry_run=0, notes=None):
    assert_action("run_pe_sandbox_readiness_freeze")

    items = []
    sandbox_enabled, production_mode = evaluate_config(items)
    evaluate_health(items)
    evidence = evaluate_evidence(items)
    hygiene = evaluate_hygiene(items)
    guardrails = evaluate_guardrails(items)

    ack_ok = acknowledgement == FREEZE_ACK
    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "freeze_ack", "Freeze acknowledgement", "Exact readiness freeze acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "freeze_ack", "Freeze acknowledgement", f"Required acknowledgement not supplied. Required: {FREEZE_ACK}", "Provide exact acknowledgement to allow readiness freeze.")

    summary = summarise_items(items)
    score = calculate_score(summary["blocker_count"], summary["warning_count"])
    final_readiness_status = readiness_status(score, summary["blocker_count"], summary["warning_count"])
    readiness_allowed = int(summary["blocker_count"] == 0 and ack_ok)
    ready_for_next_design_phase = int(readiness_allowed and final_readiness_status in ["Ready For Next Design Phase", "Ready With Warnings"])

    if summary["blocker_count"]:
        status = "Blocked"
    elif not ack_ok or summary["warning_count"]:
        status = "Needs Review"
    else:
        status = "Frozen"

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "freeze_type": freeze_type,
        "status": status,
        "readiness_allowed": readiness_allowed,
        "ready_for_next_design_phase": ready_for_next_design_phase,
        "readiness_score": score,
        "readiness_status": final_readiness_status,
        "required_acknowledgement": FREEZE_ACK,
        "acknowledgement_ok": ack_ok,
        "summary": summary,
        "evidence": evidence,
        "hygiene": hygiene,
        "guardrails": guardrails,
        "items": items,
        "note": "Readiness freeze only. No Payment Entry, Sales Invoice, Journal Entry, Purchase Invoice or GL record is created, changed, cancelled or deleted.",
    }

    if int(dry_run or 0):
        return result

    doc = frappe.new_doc(FREEZE_DOCTYPE)
    doc.freeze_id = make_freeze_id()
    doc.status = status
    doc.freeze_type = freeze_type
    doc.readiness_allowed = readiness_allowed
    doc.ready_for_next_design_phase = ready_for_next_design_phase
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = sandbox_enabled
    doc.production_mode_detected = production_mode
    doc.frozen_on = now_datetime()
    doc.frozen_by = frappe.session.user
    doc.readiness_score = score
    doc.readiness_status = final_readiness_status
    doc.blocker_count = summary["blocker_count"]
    doc.warning_count = summary["warning_count"]
    doc.pass_count = summary["pass_count"]
    doc.info_count = summary["info_count"]
    doc.item_count = summary["item_count"]

    for fieldname, value in evidence.items():
        setattr(doc, fieldname, value)
    for fieldname, value in hygiene.items():
        setattr(doc, fieldname, value)
    for fieldname, value in guardrails.items():
        setattr(doc, fieldname, value)

    doc.required_acknowledgement = FREEZE_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    for item in items:
        row = frappe.new_doc(FREEZE_ITEM_DOCTYPE)
        row.readiness_freeze = doc.name
        row.status = item["status"]
        row.severity = item["severity"]
        row.category = item["category"]
        row.check_key = item["check_key"]
        row.check_label = item["check_label"]
        row.detail = item["detail"]
        row.recommendation = item.get("recommendation")
        row.source_doctype = item.get("source_doctype")
        row.source_name = item.get("source_name")
        row.checked_on = doc.frozen_on
        row.insert(ignore_permissions=True)

    frappe.db.commit()
    result["created"] = True
    result["readiness_freeze"] = doc.name
    result["freeze_id"] = doc.freeze_id
    return result


@frappe.whitelist()
def cancel_pe_sandbox_readiness_freeze(readiness_freeze, reason=None):
    assert_action("cancel_pe_sandbox_readiness_freeze")

    if not frappe.db.exists(FREEZE_DOCTYPE, readiness_freeze):
        frappe.throw(_("PE Sandbox Readiness Freeze not found: {0}").format(readiness_freeze))

    frappe.db.set_value(
        FREEZE_DOCTYPE,
        readiness_freeze,
        {
            "status": "Cancelled",
            "readiness_allowed": 0,
            "ready_for_next_design_phase": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Payment Entry sandbox readiness freeze cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        """
        UPDATE `tabNDIS PE Sandbox Readiness Freeze Item`
        SET status = 'Cancelled'
        WHERE readiness_freeze = %(readiness_freeze)s
        """,
        {"readiness_freeze": readiness_freeze},
    )
    frappe.db.commit()

    return {
        "readiness_freeze": readiness_freeze,
        "status": "Cancelled",
        "note": "Readiness freeze cancelled only. No accounting/payment records were changed.",
    }


@frappe.whitelist()
def quick_pe_sandbox_readiness_freeze_summary(limit=20):
    freezes = frappe.get_all(
        FREEZE_DOCTYPE,
        fields=[
            "name",
            "freeze_id",
            "status",
            "readiness_allowed",
            "ready_for_next_design_phase",
            "readiness_score",
            "readiness_status",
            "blocker_count",
            "warning_count",
            "draft_sandbox_pe_count",
            "submitted_sandbox_pe_count",
            "payment_entry_gl_count",
            "submitted_sandbox_si_count",
            "cancelled_sandbox_si_count",
            "sandbox_si_gl_net",
            "frozen_on",
            "frozen_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        FREEZE_ITEM_DOCTYPE,
        fields=["name", "readiness_freeze", "status", "severity", "category", "check_label", "detail", "recommendation", "source_doctype", "source_name"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "freezes": freezes,
        "items": items,
        "required_acknowledgement": FREEZE_ACK,
        "note": "Readiness freeze summary only. No accounting/payment movement created.",
    }


def execute_freeze_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("f.status = %(status)s")
        params["status"] = filters.status
    if filters.get("readiness_status"):
        conditions.append("f.readiness_status = %(readiness_status)s")
        params["readiness_status"] = filters.readiness_status
    if filters.get("from_date"):
        conditions.append("DATE(f.frozen_on) >= %(from_date)s")
        params["from_date"] = filters.from_date
    if filters.get("to_date"):
        conditions.append("DATE(f.frozen_on) <= %(to_date)s")
        params["to_date"] = filters.to_date

    columns = [
        {"fieldname": "readiness_freeze", "label": _("Readiness Freeze"), "fieldtype": "Link", "options": FREEZE_DOCTYPE, "width": 220},
        {"fieldname": "freeze_id", "label": _("Freeze ID"), "fieldtype": "Data", "width": 330},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "readiness_allowed", "label": _("Allowed"), "fieldtype": "Check", "width": 90},
        {"fieldname": "ready_for_next_design_phase", "label": _("Next Phase"), "fieldtype": "Check", "width": 100},
        {"fieldname": "readiness_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "readiness_status", "label": _("Readiness Status"), "fieldtype": "Data", "width": 220},
        {"fieldname": "blocker_count", "label": _("Blockers"), "fieldtype": "Int", "width": 90},
        {"fieldname": "warning_count", "label": _("Warnings"), "fieldtype": "Int", "width": 90},
        {"fieldname": "draft_sandbox_pe_count", "label": _("Draft PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_gl_count", "label": _("PE GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "submitted_sandbox_si_count", "label": _("Submitted SI"), "fieldtype": "Int", "width": 110},
        {"fieldname": "cancelled_sandbox_si_count", "label": _("Cancelled SI"), "fieldtype": "Int", "width": 110},
        {"fieldname": "sandbox_si_gl_net", "label": _("SI GL Net"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "frozen_on", "label": _("Frozen On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT f.name AS readiness_freeze, f.freeze_id, f.status, f.readiness_allowed,
            f.ready_for_next_design_phase, f.readiness_score, f.readiness_status,
            f.blocker_count, f.warning_count, f.draft_sandbox_pe_count,
            f.payment_entry_gl_count, f.submitted_sandbox_si_count,
            f.cancelled_sandbox_si_count, f.sandbox_si_gl_net, f.frozen_on,
            %(currency)s AS currency
        FROM `tabNDIS PE Sandbox Readiness Freeze` f
        {build_where(conditions)}
        ORDER BY f.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.freeze_id for row in data[:20]],
            "datasets": [
                {"name": "Score", "values": [flt(row.readiness_score) for row in data[:20]]},
                {"name": "Blockers", "values": [int(row.blocker_count or 0) for row in data[:20]]},
                {"name": "Warnings", "values": [int(row.warning_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Freezes"), "datatype": "Int"},
        {"value": len([row for row in data if row.readiness_allowed]), "indicator": "Green", "label": _("Allowed"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Blocked"]), "indicator": "Red", "label": _("Blocked"), "datatype": "Int"},
        {"value": len([row for row in data if row.ready_for_next_design_phase]), "indicator": "Green", "label": _("Next Phase Ready"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_freeze_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    for key in ["readiness_freeze", "status", "severity", "category"]:
        if filters.get(key):
            conditions.append(f"i.{key} = %({key})s")
            params[key] = filters.get(key)

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": FREEZE_ITEM_DOCTYPE, "width": 220},
        {"fieldname": "readiness_freeze", "label": _("Readiness Freeze"), "fieldtype": "Link", "options": FREEZE_DOCTYPE, "width": 220},
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
        SELECT i.name AS item, i.readiness_freeze, i.status, i.severity, i.category,
            i.check_label, i.detail, i.recommendation, i.source_doctype,
            i.source_name, i.checked_on
        FROM `tabNDIS PE Sandbox Readiness Freeze Item` i
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


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
