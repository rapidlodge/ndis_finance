import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


COMPLETION_ACK = "I_CONFIRM_NDIS_ACCOUNTING_SANDBOX_CHAIN_REVIEWED"

PHASE_HEALTH_CHECKS = [
    ("Phase 2A", "ndis_finance.setup.phase2a.health_check"),
    ("Phase 2B", "ndis_finance.setup.phase2b.health_check"),
    ("Phase 2C", "ndis_finance.setup.phase2c.health_check"),
    ("Phase 2D", "ndis_finance.setup.phase2d.health_check"),
    ("Phase 2E", "ndis_finance.setup.phase2e.health_check"),
    ("Phase 1Z", "ndis_finance.setup.phase1z.health_check"),
]


def make_gate_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-ACC-SANDBOX-GATE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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
                    "Review the phase health output before moving beyond sandbox accounting.",
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
    add_item(
        items,
        "Pass" if sandbox_enabled else "Warning",
        "Low" if sandbox_enabled else "Medium",
        "Site Config",
        "sandbox_config",
        "Sandbox posting config",
        "Sandbox posting config is enabled." if sandbox_enabled else "Sandbox posting config is not enabled.",
        None if sandbox_enabled else "Enable it only in dev/sandbox when testing accounting adapters.",
    )
    add_item(
        items,
        "Blocker" if production_mode else "Pass",
        "Critical" if production_mode else "Low",
        "Site Config",
        "production_mode",
        "Production mode",
        "Production mode flag is enabled." if production_mode else "Production mode flag is not enabled.",
        "Disable production mode before sandbox accounting testing." if production_mode else None,
    )
    return sandbox_enabled, production_mode


def evaluate_readiness(items):
    count = frappe.db.count("NDIS Finance Production Readiness Check", {"production_ready_allowed": 1, "status": ["in", ["Passed", "Needs Review"]]})
    latest = frappe.get_all(
        "NDIS Finance Production Readiness Check",
        filters={"production_ready_allowed": 1, "status": ["in", ["Passed", "Needs Review"]]},
        fields=["name"],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    if count:
        add_item(items, "Pass", "Low", "Readiness Gate", "allowed_readiness", "Allowed production readiness check", f"{count} allowed readiness check(s) found.", None, "NDIS Finance Production Readiness Check", latest[0].name if latest else None)
    else:
        add_item(items, "Blocker", "Critical", "Readiness Gate", "allowed_readiness", "Allowed production readiness check", "No allowed readiness check found.", "Run Phase 2A readiness gate and acknowledge it before continuing.")
    return count


def evaluate_governance(items):
    count = frappe.db.count("NDIS Executive Governance Pack", {"status": "Signed Off", "management_sign_off": 1})
    latest = frappe.get_all("NDIS Executive Governance Pack", filters={"status": "Signed Off", "management_sign_off": 1}, fields=["name"], order_by="pack_date desc, creation desc", limit=1)
    if count:
        add_item(items, "Pass", "Low", "Governance", "signed_governance_pack", "Signed governance pack", f"{count} signed governance pack(s) found.", None, "NDIS Executive Governance Pack", latest[0].name if latest else None)
    else:
        add_item(items, "Warning", "High", "Governance", "signed_governance_pack", "Signed governance pack", "No signed governance pack found.", "Sign off a governance pack before moving beyond sandbox design.")
    return count


def evaluate_policies(items):
    active_count = frappe.db.count("NDIS Accounting Posting Policy", {"active": 1, "policy_status": "Active"})
    unsafe_policy_count = frappe.db.count("NDIS Accounting Posting Policy", {"active": 1, "policy_status": "Active", "allow_gl_entry": 1})
    future_posting_flag_count = frappe.db.sql(
        """
        SELECT COUNT(*) AS count
        FROM `tabNDIS Accounting Posting Policy`
        WHERE active = 1
        AND policy_status = 'Active'
        AND (allow_sales_invoice = 1 OR allow_payment_entry = 1 OR allow_journal_entry = 1 OR allow_gl_entry = 1)
        """,
        as_dict=True,
    )[0].count
    add_item(items, "Pass" if active_count >= 7 else "Warning", "Low" if active_count >= 7 else "Medium", "Posting Policies", "active_policies", "Active posting policies", f"{active_count} active posting policies found.", None if active_count >= 7 else "Review Phase 2B default policy seeding.")
    add_item(items, "Blocker" if unsafe_policy_count else "Pass", "Critical" if unsafe_policy_count else "Low", "Posting Policies", "unsafe_gl_policy", "Unsafe GL policy flag", f"{unsafe_policy_count} active policy/policies allow direct GL Entry." if unsafe_policy_count else "No active policy allows direct GL Entry.", "Direct GL Entry creation must stay blocked." if unsafe_policy_count else None)
    add_item(items, "Warning" if future_posting_flag_count else "Pass", "High" if future_posting_flag_count else "Low", "Posting Policies", "future_posting_flags", "Future posting flags", f"{future_posting_flag_count} active policy/policies have future posting flags enabled." if future_posting_flag_count else "No future live-posting flags enabled.", "Treat these as design flags only until a later controlled phase." if future_posting_flag_count else None)
    return active_count, unsafe_policy_count


def evaluate_requests(items):
    approved_dry_run_count = frappe.db.count("NDIS Accounting Posting Request", {"status": "Dry Run Passed", "approval_status": "Approved", "real_posting_enabled": 0, "hard_posting_block": 1})
    blocker_request_count = frappe.db.count("NDIS Accounting Posting Request", {"status": ["in", ["Blocked", "Dry Run Failed"]]})
    latest = frappe.get_all("NDIS Accounting Posting Request", filters={"status": "Dry Run Passed", "approval_status": "Approved"}, fields=["name"], order_by="creation desc", limit=1)
    if approved_dry_run_count:
        add_item(items, "Pass", "Low", "Posting Requests", "approved_dry_run_requests", "Approved dry-run posting requests", f"{approved_dry_run_count} approved dry-run passed request(s) found.", None, "NDIS Accounting Posting Request", latest[0].name if latest else None)
    else:
        add_item(items, "Blocker", "Critical", "Posting Requests", "approved_dry_run_requests", "Approved dry-run posting requests", "No approved Dry Run Passed posting request found.", "Complete Phase 2C approval and dry-run simulation before completion gate.")
    add_item(items, "Warning" if blocker_request_count else "Pass", "Medium" if blocker_request_count else "Low", "Posting Requests", "blocked_requests", "Blocked/dry-run failed requests", f"{blocker_request_count} blocked or dry-run failed request(s) found." if blocker_request_count else "No blocked or dry-run failed posting requests found.", "Review failed request records before future accounting design." if blocker_request_count else None)
    return approved_dry_run_count


def evaluate_sandbox_runs(items):
    sandbox_run_count = frappe.db.count("NDIS Sandbox Accounting Posting Run", {"status": ["in", ["Created Draft JE", "Cancelled"]]})
    created_draft_count = frappe.db.count("NDIS Sandbox Accounting Posting Run", {"status": "Created Draft JE"})
    if sandbox_run_count:
        add_item(items, "Pass", "Low", "Sandbox JE Adapter", "sandbox_draft_je_runs", "Sandbox Draft JE run evidence", f"{sandbox_run_count} sandbox accounting run(s) found.")
    else:
        add_item(items, "Blocker", "Critical", "Sandbox JE Adapter", "sandbox_draft_je_runs", "Sandbox Draft JE run evidence", "No Phase 2D sandbox accounting run found.", "Run Phase 2D sandbox draft JE test before completion gate.")
    add_item(items, "Pass" if created_draft_count else "Warning", "Low" if created_draft_count else "Medium", "Sandbox JE Adapter", "created_draft_je_runs", "Created Draft JE run evidence", f"{created_draft_count} sandbox run(s) show Created Draft JE evidence." if created_draft_count else "No sandbox run currently has status Created Draft JE.", None if created_draft_count else "This may be acceptable if cleanup/cancellation changed state, but confirm Phase 2D evidence exists.")
    return sandbox_run_count


def evaluate_cleanup(items):
    cleaned_count = frappe.db.count("NDIS Sandbox Accounting Cleanup Run", {"status": "Cleaned"})
    preview_count = frappe.db.count("NDIS Sandbox Accounting Cleanup Run", {"status": "Previewed"})
    add_item(items, "Pass" if cleaned_count else "Warning", "Low" if cleaned_count else "High", "Sandbox Cleanup", "cleaned_cleanup_runs", "Cleaned cleanup run evidence", f"{cleaned_count} cleaned cleanup run(s) found." if cleaned_count else "No cleaned cleanup run found.", None if cleaned_count else "Run Phase 2E cleanup deletion test for sandbox draft JEs.")
    add_item(items, "Pass" if preview_count else "Info", "Low", "Sandbox Cleanup", "preview_cleanup_runs", "Preview cleanup run evidence", f"{preview_count} preview cleanup run(s) found." if preview_count else "No preview cleanup run found.")
    return cleaned_count


def get_sandbox_gl_entry_count():
    if not frappe.db.exists("DocType", "GL Entry"):
        return 0
    je_names = set()
    for row in frappe.get_all("Journal Entry", filters={"custom_ndis_sandbox_draft_only": 1}, fields=["name"], limit=10000):
        je_names.add(row.name)
    for row in frappe.get_all("NDIS Sandbox Accounting Cleanup Line", fields=["journal_entry"], limit=10000):
        if row.journal_entry:
            je_names.add(row.journal_entry)
    for row in frappe.get_all("NDIS Sandbox Accounting Posting Run", fields=["journal_entry"], limit=10000):
        if row.journal_entry:
            je_names.add(row.journal_entry)
    if not je_names:
        return 0
    return frappe.db.count("GL Entry", {"voucher_type": "Journal Entry", "voucher_no": ["in", list(je_names)]})


def evaluate_hygiene(items, stale_age_days=7):
    draft_count = frappe.db.count("Journal Entry", {"custom_ndis_sandbox_draft_only": 1, "docstatus": 0})
    submitted_count = frappe.db.count("Journal Entry", {"custom_ndis_sandbox_draft_only": 1, "docstatus": 1})
    stale_count = frappe.db.sql(
        """
        SELECT COUNT(*) AS count
        FROM `tabJournal Entry`
        WHERE custom_ndis_sandbox_draft_only = 1
        AND docstatus = 0
        AND DATE(creation) <= DATE_SUB(CURDATE(), INTERVAL %(stale_age_days)s DAY)
        """,
        {"stale_age_days": int(stale_age_days or 7)},
        as_dict=True,
    )[0].count
    sandbox_gl_count = get_sandbox_gl_entry_count()
    add_item(items, "Blocker" if submitted_count else "Pass", "Critical" if submitted_count else "Low", "Sandbox Hygiene", "submitted_sandbox_journal_entries", "Submitted sandbox Journal Entries", f"{submitted_count} submitted sandbox JE(s) found." if submitted_count else "No submitted sandbox Journal Entries found.", "Submitted sandbox JEs should never exist." if submitted_count else None)
    add_item(items, "Blocker" if sandbox_gl_count else "Pass", "Critical" if sandbox_gl_count else "Low", "Sandbox Hygiene", "sandbox_gl_entries", "GL Entries linked to sandbox JEs", f"{sandbox_gl_count} GL Entry record(s) linked to sandbox JE evidence." if sandbox_gl_count else "No GL Entries linked to sandbox JE evidence found.", "Investigate immediately. Sandbox JEs must not create GL Entries." if sandbox_gl_count else None)
    add_item(items, "Warning" if stale_count else "Pass", "High" if stale_count else "Low", "Sandbox Hygiene", "stale_draft_sandbox_journal_entries", "Stale draft sandbox JEs", f"{stale_count} draft sandbox JE(s) older than {int(stale_age_days or 7)} day(s)." if stale_count else "No stale draft sandbox JEs found.", "Run Phase 2E cleanup." if stale_count else None)
    add_item(items, "Warning" if draft_count else "Pass", "Medium" if draft_count else "Low", "Sandbox Hygiene", "draft_sandbox_journal_entries", "Remaining draft sandbox JEs", f"{draft_count} draft sandbox JE(s) remain." if draft_count else "No remaining draft sandbox JEs found.", "This is acceptable only for active testing. Clean up old records before future live-posting design." if draft_count else None)
    return draft_count, submitted_count, sandbox_gl_count, stale_count


def evaluate_movement_guardrails(items):
    counts = {
        "Payment Entry": frappe.db.count("Payment Entry", {"creation": [">=", today()]}) if frappe.db.exists("DocType", "Payment Entry") else 0,
        "Submitted Journal Entry": frappe.db.count("Journal Entry", {"creation": [">=", today()], "docstatus": 1}) if frappe.db.exists("DocType", "Journal Entry") else 0,
        "GL Entry": frappe.db.count("GL Entry", {"creation": [">=", today()]}) if frappe.db.exists("DocType", "GL Entry") else 0,
        "Sales Invoice": frappe.db.count("Sales Invoice", {"creation": [">=", today()]}) if frappe.db.exists("DocType", "Sales Invoice") else 0,
        "Purchase Invoice": frappe.db.count("Purchase Invoice", {"creation": [">=", today()]}) if frappe.db.exists("DocType", "Purchase Invoice") else 0,
    }
    total = sum(int(value or 0) for value in counts.values())
    add_item(
        items,
        "Warning" if total else "Pass",
        "Medium" if total else "Low",
        "Movement Guardrail",
        "movement_counts_today",
        "Accounting movement counts today",
        "Today counts: " + ", ".join([f"{key}={value}" for key, value in counts.items()]) if total else "No Payment Entry, submitted Journal Entry, GL Entry, Sales Invoice or Purchase Invoice created today.",
        "Confirm these are not from NDIS Finance sandbox phases." if total else None,
    )
    return counts


def calculate_score(blockers, warnings):
    return max(0, round(100 - int(blockers or 0) * 25 - int(warnings or 0) * 5, 2))


def completion_status(score, blockers, warnings):
    if blockers:
        return "Blocked"
    if score >= 90 and not warnings:
        return "Complete"
    if score >= 75:
        return "Watch"
    return "Needs Cleanup"


def summarise_items(items):
    return {
        "blocker_count": len([i for i in items if i["status"] == "Blocker"]),
        "warning_count": len([i for i in items if i["status"] == "Warning"]),
        "pass_count": len([i for i in items if i["status"] == "Pass"]),
        "info_count": len([i for i in items if i["status"] == "Info"]),
        "item_count": len(items),
    }


@frappe.whitelist()
def run_accounting_sandbox_completion_gate(gate_type="Accounting Sandbox Completion", stale_age_days=7, acknowledgement=None, dry_run=0, notes=None):
    assert_action("run_accounting_sandbox_completion_gate")
    items = []
    sandbox_config_enabled, production_mode_detected = evaluate_config(items)
    evaluate_health_checks(items)
    allowed_readiness_count = evaluate_readiness(items)
    signed_governance_pack_count = evaluate_governance(items)
    active_policy_count, unsafe_policy_count = evaluate_policies(items)
    approved_dry_run_request_count = evaluate_requests(items)
    sandbox_draft_je_run_count = evaluate_sandbox_runs(items)
    cleaned_cleanup_run_count = evaluate_cleanup(items)
    draft_sandbox_je_count, submitted_sandbox_je_count, sandbox_gl_entry_count, stale_draft_sandbox_je_count = evaluate_hygiene(items, stale_age_days=stale_age_days)
    movement_counts = evaluate_movement_guardrails(items)
    ack_ok = acknowledgement == COMPLETION_ACK
    add_item(
        items,
        "Pass" if ack_ok else "Warning",
        "Low" if ack_ok else "Medium",
        "Acknowledgement",
        "completion_acknowledgement",
        "Sandbox completion acknowledgement",
        "Exact acknowledgement supplied." if ack_ok else f"Required acknowledgement not supplied. Required: {COMPLETION_ACK}",
        None if ack_ok else "Provide exact acknowledgement to allow sandbox completion.",
    )
    summary = summarise_items(items)
    score = calculate_score(summary["blocker_count"], summary["warning_count"])
    final_completion_status = completion_status(score, summary["blocker_count"], summary["warning_count"])
    sandbox_completion_allowed = int(summary["blocker_count"] == 0 and ack_ok)
    status = "Blocked" if summary["blocker_count"] else ("Needs Review" if summary["warning_count"] or not ack_ok else "Passed")
    result = {
        "dry_run": bool(int(dry_run or 0)),
        "gate_type": gate_type,
        "status": status,
        "sandbox_completion_allowed": sandbox_completion_allowed,
        "required_acknowledgement": COMPLETION_ACK,
        "acknowledgement_ok": ack_ok,
        "summary": summary,
        "completion_score": score,
        "completion_status": final_completion_status,
        "evidence_counts": {
            "active_policy_count": active_policy_count,
            "allowed_readiness_check_count": allowed_readiness_count,
            "signed_governance_pack_count": signed_governance_pack_count,
            "approved_dry_run_request_count": approved_dry_run_request_count,
            "sandbox_draft_je_run_count": sandbox_draft_je_run_count,
            "cleaned_cleanup_run_count": cleaned_cleanup_run_count,
        },
        "hygiene_counts": {
            "draft_sandbox_je_count": draft_sandbox_je_count,
            "submitted_sandbox_je_count": submitted_sandbox_je_count,
            "sandbox_gl_entry_count": sandbox_gl_entry_count,
            "stale_draft_sandbox_je_count": stale_draft_sandbox_je_count,
            "unsafe_policy_count": unsafe_policy_count,
        },
        "movement_counts": movement_counts,
        "items": items,
        "note": "Accounting sandbox completion gate only. No accounting, payroll, STP, ABA, email, bank allocation, or payment movement created.",
    }
    if int(dry_run or 0):
        return result

    doc = frappe.new_doc("NDIS Accounting Sandbox Completion Gate")
    doc.gate_id = make_gate_id()
    doc.gate_type = gate_type
    doc.status = status
    doc.sandbox_completion_allowed = sandbox_completion_allowed
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
    doc.active_policy_count = active_policy_count
    doc.allowed_readiness_check_count = allowed_readiness_count
    doc.signed_governance_pack_count = signed_governance_pack_count
    doc.approved_dry_run_request_count = approved_dry_run_request_count
    doc.sandbox_draft_je_run_count = sandbox_draft_je_run_count
    doc.cleaned_cleanup_run_count = cleaned_cleanup_run_count
    doc.draft_sandbox_je_count = draft_sandbox_je_count
    doc.submitted_sandbox_je_count = submitted_sandbox_je_count
    doc.sandbox_gl_entry_count = sandbox_gl_entry_count
    doc.stale_draft_sandbox_je_count = stale_draft_sandbox_je_count
    doc.unsafe_policy_count = unsafe_policy_count
    doc.payment_entry_count_today = movement_counts.get("Payment Entry", 0)
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
        row = frappe.new_doc("NDIS Accounting Sandbox Completion Gate Item")
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
def cancel_accounting_sandbox_completion_gate(completion_gate, reason=None):
    assert_action("cancel_accounting_sandbox_completion_gate")
    if not frappe.db.exists("NDIS Accounting Sandbox Completion Gate", completion_gate):
        frappe.throw(_("Accounting Sandbox Completion Gate not found: {0}").format(completion_gate))
    frappe.db.set_value(
        "NDIS Accounting Sandbox Completion Gate",
        completion_gate,
        {
            "status": "Cancelled",
            "sandbox_completion_allowed": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "warning_log": reason or "Sandbox completion gate cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        """
        UPDATE `tabNDIS Accounting Sandbox Completion Gate Item`
        SET status = 'Cancelled'
        WHERE completion_gate = %(completion_gate)s
        """,
        {"completion_gate": completion_gate},
    )
    frappe.db.commit()
    return {"completion_gate": completion_gate, "status": "Cancelled", "note": "Completion gate cancelled only. No accounting/payroll/payment records were changed."}


@frappe.whitelist()
def quick_accounting_sandbox_completion_summary(limit=20):
    gates = frappe.get_all(
        "NDIS Accounting Sandbox Completion Gate",
        fields=[
            "name",
            "gate_id",
            "gate_type",
            "status",
            "sandbox_completion_allowed",
            "completion_score",
            "completion_status",
            "blocker_count",
            "warning_count",
            "draft_sandbox_je_count",
            "submitted_sandbox_je_count",
            "sandbox_gl_entry_count",
            "stale_draft_sandbox_je_count",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        "NDIS Accounting Sandbox Completion Gate Item",
        fields=["name", "completion_gate", "status", "severity", "category", "check_label", "detail", "recommendation", "source_doctype", "source_name"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "gates": gates,
        "items": items,
        "required_acknowledgement": COMPLETION_ACK,
        "note": "Sandbox completion summary only. No accounting, payroll, STP, ABA, email, bank allocation, or payment movement created.",
    }


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
    if filters.get("from_date"):
        conditions.append("DATE(g.checked_on) >= %(from_date)s")
        params["from_date"] = filters.get("from_date")
    if filters.get("to_date"):
        conditions.append("DATE(g.checked_on) <= %(to_date)s")
        params["to_date"] = filters.get("to_date")
    columns = [
        {"fieldname": "completion_gate", "label": _("Completion Gate"), "fieldtype": "Link", "options": "NDIS Accounting Sandbox Completion Gate", "width": 220},
        {"fieldname": "gate_id", "label": _("Gate ID"), "fieldtype": "Data", "width": 310},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "sandbox_completion_allowed", "label": _("Allowed"), "fieldtype": "Check", "width": 90},
        {"fieldname": "completion_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "completion_status", "label": _("Completion Status"), "fieldtype": "Data", "width": 150},
        {"fieldname": "blocker_count", "label": _("Blockers"), "fieldtype": "Int", "width": 90},
        {"fieldname": "warning_count", "label": _("Warnings"), "fieldtype": "Int", "width": 90},
        {"fieldname": "approved_dry_run_request_count", "label": _("Dry-run Requests"), "fieldtype": "Int", "width": 130},
        {"fieldname": "sandbox_draft_je_run_count", "label": _("Sandbox Runs"), "fieldtype": "Int", "width": 120},
        {"fieldname": "cleaned_cleanup_run_count", "label": _("Cleanups"), "fieldtype": "Int", "width": 100},
        {"fieldname": "draft_sandbox_je_count", "label": _("Draft Sandbox JEs"), "fieldtype": "Int", "width": 130},
        {"fieldname": "submitted_sandbox_je_count", "label": _("Submitted Sandbox JEs"), "fieldtype": "Int", "width": 150},
        {"fieldname": "sandbox_gl_entry_count", "label": _("Sandbox GL"), "fieldtype": "Int", "width": 100},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "checked_by", "label": _("Checked By"), "fieldtype": "Link", "options": "User", "width": 160},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            g.name AS completion_gate,
            g.gate_id,
            g.status,
            g.sandbox_completion_allowed,
            g.completion_score,
            g.completion_status,
            g.blocker_count,
            g.warning_count,
            g.approved_dry_run_request_count,
            g.sandbox_draft_je_run_count,
            g.cleaned_cleanup_run_count,
            g.draft_sandbox_je_count,
            g.submitted_sandbox_je_count,
            g.sandbox_gl_entry_count,
            g.checked_on,
            g.checked_by
        FROM `tabNDIS Accounting Sandbox Completion Gate` g
        {build_where(conditions)}
        ORDER BY g.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {"data": {"labels": [row.gate_id for row in data[:20]], "datasets": [{"name": "Score", "values": [flt(row.completion_score) for row in data[:20]]}, {"name": "Blockers", "values": [int(row.blocker_count or 0) for row in data[:20]]}, {"name": "Warnings", "values": [int(row.warning_count or 0) for row in data[:20]]}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Gates"), "datatype": "Int"},
        {"value": len([row for row in data if row.sandbox_completion_allowed]), "indicator": "Green", "label": _("Allowed"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Blocked"]), "indicator": "Red", "label": _("Blocked"), "datatype": "Int"},
        {"value": data[0].completion_score if data else 0, "indicator": "Green" if data and flt(data[0].completion_score) >= 90 else "Orange", "label": _("Latest Score"), "datatype": "Percent"},
    ]
    return columns, data, None, chart, summary


def execute_completion_exception_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    for fieldname in ["completion_gate", "status", "severity", "category"]:
        if filters.get(fieldname):
            conditions.append(f"i.{fieldname} = %({fieldname})s")
            params[fieldname] = filters.get(fieldname)
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "NDIS Accounting Sandbox Completion Gate Item", "width": 220},
        {"fieldname": "completion_gate", "label": _("Completion Gate"), "fieldtype": "Link", "options": "NDIS Accounting Sandbox Completion Gate", "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 180},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 280},
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
        FROM `tabNDIS Accounting Sandbox Completion Gate Item` i
        {build_where(conditions)}
        ORDER BY
            CASE i.status WHEN 'Blocker' THEN 1 WHEN 'Warning' THEN 2 WHEN 'Info' THEN 3 WHEN 'Pass' THEN 4 ELSE 5 END,
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
