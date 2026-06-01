import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


FREEZE_DOCTYPE = "NDIS Real Remittance PE Evidence Freeze"
ITEM_DOCTYPE = "NDIS Real Remittance PE Evidence Freeze Item"
FREEZE_ACK = "I_CONFIRM_PHASE6H_FREEZE_REAL_REMITTANCE_PE_SMOKE_ROLLBACK_EVIDENCE"


def make_freeze_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-REAL-REMITTANCE-PE-FREEZE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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
        "submitted_smoke_pe_count": count_dt("Payment Entry", {"docstatus": 1, "custom_ndis_real_remittance_pe_smoke": 1}),
        "cancelled_smoke_pe_count": count_dt("Payment Entry", {"docstatus": 2, "custom_ndis_real_remittance_pe_smoke": 1}),
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
        "live_enabled_policy_count": count_dt("NDIS PE Production Posting Policy", {"production_posting_enabled": 1}),
    }


def latest_rollback_run():
    rows = frappe.get_all(
        "NDIS Real Remittance PE Rollback Run",
        filters={
            "status": "Rolled Back",
            "rollback_allowed": 1,
            "payment_entry_cancelled": 1,
            "source_invoice_restored": 1,
            "real_posting_allowed": 0,
        },
        fields=["name"],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0].name if rows else None


def get_doc_if_exists(doctype, name):
    if name and frappe.db.exists(doctype, name):
        return frappe.get_doc(doctype, name)
    return None


def gl_count(voucher_type, voucher_no):
    if not voucher_no:
        return 0
    return count_dt("GL Entry", {"voucher_type": voucher_type, "voucher_no": voucher_no})


def gl_net(voucher_type, voucher_no):
    if not voucher_no:
        return 0
    value = frappe.db.sql(
        """
        SELECT COALESCE(SUM(debit - credit), 0)
        FROM `tabGL Entry`
        WHERE voucher_type = %(voucher_type)s
        AND voucher_no = %(voucher_no)s
        """,
        {"voucher_type": voucher_type, "voucher_no": voucher_no},
    )[0][0]
    return flt(value, 2)


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


def collect_evidence(rollback_run=None):
    if rollback_run:
        if not frappe.db.exists("NDIS Real Remittance PE Rollback Run", rollback_run):
            frappe.throw(_("Rollback run not found: {0}").format(rollback_run))
        rollback = frappe.get_doc("NDIS Real Remittance PE Rollback Run", rollback_run)
    else:
        latest = latest_rollback_run()
        rollback = frappe.get_doc("NDIS Real Remittance PE Rollback Run", latest) if latest else None

    smoke = get_doc_if_exists("NDIS Real Remittance PE Smoke Run", rollback.smoke_run) if rollback else None
    harness = get_doc_if_exists("NDIS Real Remittance PE Source Harness Run", rollback.source_harness_run) if rollback else None
    activation = get_doc_if_exists("NDIS Real Remittance PE Activation Gate", getattr(smoke, "activation_gate", None)) if smoke else None
    adapter = get_doc_if_exists("NDIS Real Remittance PE Adapter Run", getattr(smoke, "adapter_run", None)) if smoke else None
    preview = get_doc_if_exists("NDIS Real Remittance PE Preview", getattr(smoke, "preview", None)) if smoke else None
    design = get_doc_if_exists("NDIS Real Remittance PE Design Gate", getattr(activation, "design_gate", None)) if activation else None
    pe = get_doc_if_exists("Payment Entry", rollback.payment_entry) if rollback else None
    si = get_doc_if_exists("Sales Invoice", rollback.sales_invoice) if rollback else None
    return {
        "rollback": rollback,
        "smoke": smoke,
        "harness": harness,
        "activation": activation,
        "adapter": adapter,
        "preview": preview,
        "design": design,
        "payment_entry_doc": pe,
        "sales_invoice_doc": si,
    }


def evaluate_config(items, config):
    add_item(items, "Blocker" if config["production_mode"] else "Pass", "Critical" if config["production_mode"] else "Low", "Site Config", "production_mode", "Production mode", "Production mode is enabled." if config["production_mode"] else "Production mode remains disabled.")
    add_item(items, "Blocker" if config["live_pe_enabled"] else "Pass", "Critical" if config["live_pe_enabled"] else "Low", "Site Config", "live_pe_enabled", "Live PE posting config", "Live Payment Entry posting config is enabled." if config["live_pe_enabled"] else "Live Payment Entry posting remains disabled.")
    add_item(items, "Pass" if config["sandbox_enabled"] else "Warning", "Low" if config["sandbox_enabled"] else "Medium", "Site Config", "sandbox_enabled", "Sandbox config", "Sandbox config remains enabled." if config["sandbox_enabled"] else "Sandbox config is not enabled.")


def evaluate_chain(items, evidence):
    rollback = evidence["rollback"]
    smoke = evidence["smoke"]
    harness = evidence["harness"]
    activation = evidence["activation"]
    adapter = evidence["adapter"]
    preview = evidence["preview"]
    design = evidence["design"]
    pe = evidence["payment_entry_doc"]
    si = evidence["sales_invoice_doc"]

    if design:
        add_item(items, "Pass", "Low", "Phase 6A", "design_gate", "Design gate exists", f"Design gate found: {design.name}.", None, "NDIS Real Remittance PE Design Gate", design.name)
    else:
        add_item(items, "Blocker", "Critical", "Phase 6A", "design_gate", "Design gate exists", "Missing Phase 6A design gate evidence.")

    if preview and int(getattr(preview, "eligible_line_count", 0) or 0) >= 1:
        add_item(items, "Pass", "Low", "Phase 6B", "preview_eligible", "Preview eligible line", f"Eligible lines: {preview.eligible_line_count}.", None, "NDIS Real Remittance PE Preview", preview.name)
    else:
        add_item(items, "Blocker", "Critical", "Phase 6B", "preview_eligible", "Preview eligible line", "Phase 6B preview does not show an eligible line.")

    if adapter and int(getattr(adapter, "hard_blocked_line_count", 0) or 0) >= 1 and int(getattr(adapter, "actual_payment_entry_created_count", 0) or 0) == 0:
        add_item(items, "Pass", "Low", "Phase 6C", "adapter_hard_block", "Adapter hard-block evidence", f"Hard-blocked lines: {adapter.hard_blocked_line_count}, actual PE created: 0.", None, "NDIS Real Remittance PE Adapter Run", adapter.name)
    else:
        add_item(items, "Blocker", "Critical", "Phase 6C", "adapter_hard_block", "Adapter hard-block evidence", "Phase 6C hard-block evidence is missing or invalid.")

    if activation and int(getattr(activation, "ready_for_real_smoke", 0) or 0) == 1 and int(getattr(activation, "real_posting_allowed", 0) or 0) == 0:
        add_item(items, "Pass", "Low", "Phase 6D", "activation_ready", "Activation ready evidence", "Ready for single real smoke with real posting still disabled.", None, "NDIS Real Remittance PE Activation Gate", activation.name)
    else:
        add_item(items, "Blocker", "Critical", "Phase 6D", "activation_ready", "Activation ready evidence", "Phase 6D activation evidence is missing or invalid.")

    if harness and getattr(harness, "sales_invoice", None):
        add_item(items, "Pass", "Low", "Phase 6E", "source_harness", "Controlled source harness", f"Source harness found: {harness.name}.", None, "NDIS Real Remittance PE Source Harness Run", harness.name)
    else:
        add_item(items, "Blocker", "Critical", "Phase 6E", "source_harness", "Controlled source harness", "Phase 6E source harness evidence is missing.")

    if smoke and int(getattr(smoke, "payment_entry_submitted", 0) or 0) == 1 and getattr(smoke, "payment_entry", None):
        add_item(items, "Pass", "Low", "Phase 6F", "smoke_submitted", "One PE smoke submitted", f"Smoke Payment Entry: {smoke.payment_entry}.", None, "NDIS Real Remittance PE Smoke Run", smoke.name)
    else:
        add_item(items, "Blocker", "Critical", "Phase 6F", "smoke_submitted", "One PE smoke submitted", "Phase 6F smoke evidence is missing or invalid.")

    if rollback and int(getattr(rollback, "payment_entry_cancelled", 0) or 0) == 1 and int(getattr(rollback, "source_invoice_restored", 0) or 0) == 1:
        add_item(items, "Pass", "Low", "Phase 6G", "rollback_complete", "Rollback completed", f"Rollback run found: {rollback.name}.", None, "NDIS Real Remittance PE Rollback Run", rollback.name)
    else:
        add_item(items, "Blocker", "Critical", "Phase 6G", "rollback_complete", "Rollback completed", "Phase 6G rollback evidence is missing or invalid.")

    if pe and pe.docstatus == 2:
        add_item(items, "Pass", "Low", "Payment Entry", "pe_cancelled", "Controlled Payment Entry cancelled", f"{pe.name} docstatus is 2.", None, "Payment Entry", pe.name)
    else:
        add_item(items, "Blocker", "Critical", "Payment Entry", "pe_cancelled", "Controlled Payment Entry cancelled", "Controlled Payment Entry is not cancelled.")

    if pe and gl_count("Payment Entry", pe.name) == 4 and gl_net("Payment Entry", pe.name) == 0:
        add_item(items, "Pass", "Low", "Payment Entry GL", "pe_gl_reversed", "Payment Entry GL reversed", "4 GL rows found and net is 0.00.", None, "Payment Entry", pe.name)
    else:
        add_item(items, "Blocker", "Critical", "Payment Entry GL", "pe_gl_reversed", "Payment Entry GL reversed", "Payment Entry GL does not show 4 balanced rows.")

    if si and si.docstatus == 1 and flt(si.outstanding_amount, 2) == 1:
        add_item(items, "Pass", "Low", "Sales Invoice", "si_restored", "Controlled invoice restored", f"{si.name} remains submitted and outstanding is 1.00.", None, "Sales Invoice", si.name)
    else:
        add_item(items, "Blocker", "Critical", "Sales Invoice", "si_restored", "Controlled invoice restored", "Controlled Sales Invoice is not restored to submitted/outstanding 1.00 state.")


def evaluate_guardrails(items, guard):
    checks = [
        ("submitted_smoke_pe_count", guard["submitted_smoke_pe_count"] == 0, "Submitted smoke PE count", f"{guard['submitted_smoke_pe_count']} submitted smoke PE(s) found."),
        ("cancelled_smoke_pe", guard["cancelled_smoke_pe_count"] >= 1, "Cancelled smoke PE count", "No cancelled smoke PE found."),
        ("submitted_je_today", guard["submitted_journal_entry_count_today"] == 0, "Submitted JE today", f"{guard['submitted_journal_entry_count_today']} submitted Journal Entry record(s) found today."),
        ("purchase_invoice_today", guard["purchase_invoice_count_today"] == 0, "Purchase Invoice today", f"{guard['purchase_invoice_count_today']} Purchase Invoice record(s) found today."),
        ("live_enabled_policy", guard["live_enabled_policy_count"] == 0, "Live-enabled policy count", f"{guard['live_enabled_policy_count']} live-enabled policy record(s) found."),
    ]
    for key, ok, label, bad_detail in checks:
        add_item(items, "Pass" if ok else "Blocker", "Low" if ok else "Critical", "Guardrail", key, label, "Zero." if ok and key != "cancelled_smoke_pe" else (f"{guard['cancelled_smoke_pe_count']} cancelled smoke PE(s) found." if ok else bad_detail))


def summarise_items(items):
    return {
        "blocker_count": len([i for i in items if i["status"] == "Blocker"]),
        "warning_count": len([i for i in items if i["status"] == "Warning"]),
        "pass_count": len([i for i in items if i["status"] == "Pass"]),
        "info_count": len([i for i in items if i["status"] == "Info"]),
        "item_count": len(items),
    }


def calculate_score(blockers, warnings):
    score = 100 - int(blockers or 0) * 25 - int(warnings or 0) * 5
    return max(0, round(score, 2))


def create_freeze_items(doc, items):
    for item in items:
        row = frappe.new_doc(ITEM_DOCTYPE)
        row.evidence_freeze = doc.name
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


@frappe.whitelist()
def run_real_remittance_pe_evidence_freeze(rollback_run=None, dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_real_remittance_pe_evidence_freeze")
    config = config_state()
    guard_before = guardrails()
    evidence = collect_evidence(rollback_run)
    items = []
    evaluate_config(items, config)
    evaluate_chain(items, evidence)
    evaluate_guardrails(items, guard_before)

    ack_ok = acknowledgement == FREEZE_ACK
    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "freeze_ack", "Freeze acknowledgement", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "freeze_ack", "Freeze acknowledgement", f"Required acknowledgement not supplied. Required: {FREEZE_ACK}", "Provide exact acknowledgement to freeze Phase 6H evidence.")

    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    evidence_freeze_allowed = int(ack_ok and item_summary["blocker_count"] == 0)
    ready_for_next_phase = evidence_freeze_allowed
    status = "Frozen" if evidence_freeze_allowed else ("Blocked" if item_summary["blocker_count"] else "Needs Review")
    freeze_status = "Ready For Next Controlled Design Phase" if ready_for_next_phase else ("Blocked" if item_summary["blocker_count"] else "Needs Review")

    rollback = evidence["rollback"]
    smoke = evidence["smoke"]
    harness = evidence["harness"]
    activation = evidence["activation"]
    adapter = evidence["adapter"]
    preview = evidence["preview"]
    design = evidence["design"]
    pe = evidence["payment_entry_doc"]
    si = evidence["sales_invoice_doc"]
    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": status,
        "freeze_status": freeze_status,
        "freeze_score": score,
        "evidence_freeze_allowed": evidence_freeze_allowed,
        "ready_for_next_phase": ready_for_next_phase,
        "real_posting_allowed": 0,
        "design_gate": design.name if design else None,
        "preview": preview.name if preview else None,
        "adapter_run": adapter.name if adapter else None,
        "activation_gate": activation.name if activation else None,
        "source_harness_run": harness.name if harness else None,
        "smoke_run": smoke.name if smoke else None,
        "rollback_run": rollback.name if rollback else None,
        "sales_invoice": si.name if si else None,
        "payment_entry": pe.name if pe else None,
        "company": getattr(rollback, "company", None) if rollback else None,
        "customer": getattr(rollback, "customer", None) if rollback else None,
        "payment_amount": flt(getattr(rollback, "payment_amount", 0) or 0) if rollback else 0,
        "invoice_outstanding_after_rollback": flt(si.outstanding_amount) if si else 0,
        "payment_entry_docstatus_after": pe.docstatus if pe else None,
        "payment_entry_gl_count_after": gl_count("Payment Entry", pe.name) if pe else 0,
        "payment_entry_gl_net_after": gl_net("Payment Entry", pe.name) if pe else 0,
        "phase6b_eligible_line_count": int(getattr(preview, "eligible_line_count", 0) or 0) if preview else 0,
        "phase6c_hard_blocked_line_count": int(getattr(adapter, "hard_blocked_line_count", 0) or 0) if adapter else 0,
        "phase6d_ready_for_real_smoke": int(getattr(activation, "ready_for_real_smoke", 0) or 0) if activation else 0,
        "phase6f_submitted_pe_count": int(getattr(smoke, "payment_entry_submitted", 0) or 0) if smoke else 0,
        "phase6g_cancelled_pe_count": int(getattr(rollback, "payment_entry_cancelled", 0) or 0) if rollback else 0,
        "items": items,
        "summary": item_summary,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": FREEZE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 6H is read-only evidence freeze. It creates no accounting movement.",
    }
    if int(dry_run or 0):
        return result

    doc = frappe.new_doc(FREEZE_DOCTYPE)
    doc.freeze_id = make_freeze_id()
    doc.status = status
    doc.freeze_type = "Real Remittance PE Smoke And Rollback Evidence"
    doc.evidence_freeze_allowed = evidence_freeze_allowed
    doc.ready_for_next_phase = ready_for_next_phase
    doc.real_posting_allowed = 0
    for fieldname in [
        "design_gate",
        "preview",
        "adapter_run",
        "activation_gate",
        "source_harness_run",
        "smoke_run",
        "rollback_run",
        "sales_invoice",
        "payment_entry",
        "company",
        "customer",
        "payment_amount",
        "invoice_outstanding_after_rollback",
        "payment_entry_docstatus_after",
        "payment_entry_gl_count_after",
        "payment_entry_gl_net_after",
        "phase6b_eligible_line_count",
        "phase6c_hard_blocked_line_count",
        "phase6d_ready_for_real_smoke",
        "phase6f_submitted_pe_count",
        "phase6g_cancelled_pe_count",
    ]:
        setattr(doc, fieldname, result.get(fieldname))
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.freeze_score = score
    doc.freeze_status = freeze_status
    doc.blocker_count = item_summary["blocker_count"]
    doc.warning_count = item_summary["warning_count"]
    doc.pass_count = item_summary["pass_count"]
    doc.info_count = item_summary["info_count"]
    doc.item_count = item_summary["item_count"]
    doc.payment_entry_count_before = guard_before["payment_entry_count"]
    doc.payment_entry_count_after = guardrails()["payment_entry_count"]
    doc.payment_entry_gl_count_before_total = guard_before["payment_entry_gl_count"]
    doc.payment_entry_gl_count_after_total = guardrails()["payment_entry_gl_count"]
    doc.submitted_smoke_pe_count = guard_before["submitted_smoke_pe_count"]
    doc.cancelled_smoke_pe_count = guard_before["cancelled_smoke_pe_count"]
    doc.submitted_journal_entry_count_today = guard_before["submitted_journal_entry_count_today"]
    doc.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
    doc.live_enabled_policy_count = guard_before["live_enabled_policy_count"]
    doc.required_acknowledgement = FREEZE_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_freeze_items(doc, items)
    guard_after = guardrails()
    frappe.db.set_value(
        FREEZE_DOCTYPE,
        doc.name,
        {
            "payment_entry_count_after": guard_after["payment_entry_count"],
            "payment_entry_gl_count_after_total": guard_after["payment_entry_gl_count"],
            "summary_json": safe_json({**result, "guardrails_after": guard_after}),
        },
        update_modified=False,
    )
    frappe.db.commit()
    result.update({"created": True, "evidence_freeze": doc.name, "freeze_id": doc.freeze_id, "guardrails_after": guard_after})
    return result


@frappe.whitelist()
def cancel_real_remittance_pe_evidence_freeze(evidence_freeze, reason=None):
    assert_action("cancel_real_remittance_pe_evidence_freeze")
    if not frappe.db.exists(FREEZE_DOCTYPE, evidence_freeze):
        frappe.throw(_("Evidence freeze not found: {0}").format(evidence_freeze))
    doc = frappe.get_doc(FREEZE_DOCTYPE, evidence_freeze)
    if doc.status == "Cancelled":
        return {"evidence_freeze": evidence_freeze, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.ready_for_next_phase or 0):
        frappe.throw(_("Cannot cancel a ready-for-next-phase evidence freeze. Create a superseding freeze instead."))
    frappe.db.set_value(
        FREEZE_DOCTYPE,
        evidence_freeze,
        {
            "status": "Cancelled",
            "evidence_freeze_allowed": 0,
            "ready_for_next_phase": 0,
            "real_posting_allowed": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 6H evidence freeze cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{ITEM_DOCTYPE}` SET status = 'Cancelled' WHERE evidence_freeze = %(evidence_freeze)s", {"evidence_freeze": evidence_freeze})
    frappe.db.commit()
    return {"evidence_freeze": evidence_freeze, "status": "Cancelled", "note": "Evidence freeze audit record cancelled only. No accounting movement occurred."}


@frappe.whitelist()
def quick_real_remittance_pe_evidence_freeze_summary(limit=20):
    freezes = frappe.get_all(
        FREEZE_DOCTYPE,
        fields=[
            "name",
            "freeze_id",
            "status",
            "freeze_status",
            "freeze_score",
            "evidence_freeze_allowed",
            "ready_for_next_phase",
            "real_posting_allowed",
            "rollback_run",
            "smoke_run",
            "sales_invoice",
            "payment_entry",
            "payment_amount",
            "invoice_outstanding_after_rollback",
            "payment_entry_docstatus_after",
            "payment_entry_gl_count_after",
            "payment_entry_gl_net_after",
            "submitted_smoke_pe_count",
            "cancelled_smoke_pe_count",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        ITEM_DOCTYPE,
        fields=["name", "evidence_freeze", "status", "severity", "category", "check_label", "detail", "recommendation", "source_doctype", "source_name"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "freezes": freezes,
        "items": items,
        "required_acknowledgement": FREEZE_ACK,
        "guardrails": guardrails(),
        "config": config_state(),
        "note": "Phase 6H summary. Evidence freeze only, no accounting movement.",
    }


def freeze_columns():
    return [
        {"fieldname": "evidence_freeze", "label": _("Evidence Freeze"), "fieldtype": "Link", "options": FREEZE_DOCTYPE, "width": 220},
        {"fieldname": "freeze_id", "label": _("Freeze ID"), "fieldtype": "Data", "width": 360},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "freeze_status", "label": _("Freeze Status"), "fieldtype": "Data", "width": 260},
        {"fieldname": "freeze_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "ready_for_next_phase", "label": _("Ready Next Phase"), "fieldtype": "Check", "width": 140},
        {"fieldname": "real_posting_allowed", "label": _("Real Posting Allowed"), "fieldtype": "Check", "width": 150},
        {"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 170},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 170},
        {"fieldname": "payment_amount", "label": _("Payment Amount"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "invoice_outstanding_after_rollback", "label": _("Invoice Outstanding"), "fieldtype": "Currency", "options": "currency", "width": 150},
        {"fieldname": "payment_entry_docstatus_after", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL Rows"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_net_after", "label": _("PE GL Net"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "submitted_smoke_pe_count", "label": _("Submitted Smoke PE"), "fieldtype": "Int", "width": 140},
        {"fieldname": "cancelled_smoke_pe_count", "label": _("Cancelled Smoke PE"), "fieldtype": "Int", "width": 140},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_freeze_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("f.status = %(status)s")
        params["status"] = filters.status
    if filters.get("from_date"):
        conditions.append("DATE(f.checked_on) >= %(from_date)s")
        params["from_date"] = filters.from_date
    if filters.get("to_date"):
        conditions.append("DATE(f.checked_on) <= %(to_date)s")
        params["to_date"] = filters.to_date
    data = frappe.db.sql(
        f"""
        SELECT f.name AS evidence_freeze, f.freeze_id, f.status, f.freeze_status,
            f.freeze_score, f.evidence_freeze_allowed, f.ready_for_next_phase,
            f.real_posting_allowed, f.rollback_run, f.smoke_run, f.sales_invoice,
            f.payment_entry, f.payment_amount, f.invoice_outstanding_after_rollback,
            f.payment_entry_docstatus_after, f.payment_entry_gl_count_after,
            f.payment_entry_gl_net_after, f.submitted_smoke_pe_count,
            f.cancelled_smoke_pe_count, f.checked_on, %(currency)s AS currency
        FROM `tab{FREEZE_DOCTYPE}` f
        {build_where(conditions)}
        ORDER BY f.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {"data": {"labels": [row.freeze_id for row in data[:20]], "datasets": [{"name": "Ready Next Phase", "values": [int(row.ready_for_next_phase or 0) for row in data[:20]]}, {"name": "Real Posting Allowed", "values": [int(row.real_posting_allowed or 0) for row in data[:20]]}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Evidence Freezes"), "datatype": "Int"},
        {"value": sum(int(row.ready_for_next_phase or 0) for row in data), "indicator": "Green", "label": _("Ready For Next Phase"), "datatype": "Int"},
        {"value": sum(int(row.real_posting_allowed or 0) for row in data), "indicator": "Red", "label": _("Real Posting Allowed"), "datatype": "Int"},
    ]
    return freeze_columns(), data, None, chart, summary


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    for key in ["evidence_freeze", "status", "severity", "category"]:
        if filters.get(key):
            conditions.append(f"i.{key} = %({key})s")
            params[key] = filters.get(key)
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": ITEM_DOCTYPE, "width": 220},
        {"fieldname": "evidence_freeze", "label": _("Evidence Freeze"), "fieldtype": "Link", "options": FREEZE_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 160},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 320},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 520},
        {"fieldname": "recommendation", "label": _("Recommendation"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 180},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Data", "width": 220},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    data = frappe.db.sql(
        f"""
        SELECT i.name AS item, i.evidence_freeze, i.status, i.severity, i.category,
            i.check_label, i.detail, i.recommendation, i.source_doctype, i.source_name,
            i.checked_on
        FROM `tab{ITEM_DOCTYPE}` i
        {build_where(conditions)}
        ORDER BY CASE i.status WHEN 'Blocker' THEN 1 WHEN 'Warning' THEN 2 WHEN 'Info' THEN 3 WHEN 'Pass' THEN 4 ELSE 5 END, i.creation DESC
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


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_freeze_report(filters)
    summary.extend(
        [
            {"value": count_dt("Payment Entry", {"docstatus": 1, "custom_ndis_real_remittance_pe_smoke": 1}), "indicator": "Red", "label": _("Submitted Smoke PEs"), "datatype": "Int"},
            {"value": count_dt("Payment Entry", {"docstatus": 2, "custom_ndis_real_remittance_pe_smoke": 1}), "indicator": "Green", "label": _("Cancelled Smoke PEs"), "datatype": "Int"},
            {"value": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}), "indicator": "Red", "label": _("Submitted JEs Today"), "datatype": "Int"},
            {"value": count_dt("Purchase Invoice", {"creation": [">=", today()]}), "indicator": "Red", "label": _("Purchase Invoices Today"), "datatype": "Int"},
        ]
    )
    return columns, data, message, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
