import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


FREEZE_DOCTYPE = "NDIS PE Live Smoke Completion Freeze"
ITEM_DOCTYPE = "NDIS PE Live Smoke Completion Freeze Item"
FREEZE_ACK = "I_CONFIRM_FREEZE_PHASE5_PE_LIVE_SMOKE_COMPLETION"


def make_freeze_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-PE-LIVE-SMOKE-FREEZE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def latest_doc(doctype, filters=None, fields=None, order_by="creation desc"):
    rows = frappe.get_all(
        doctype,
        filters=filters or {},
        fields=fields or ["name"],
        order_by=order_by,
        limit=1,
    )
    return rows[0] if rows else None


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


def config_state():
    return {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def latest_full_rollback():
    return latest_doc(
        "NDIS PE Smoke Rollback Run",
        {
            "status": "Fully Rolled Back",
            "payment_entry_cancelled": 1,
            "source_invoice_cancelled": 1,
            "new_payment_entry_created": 0,
        },
        [
            "name",
            "rollback_run_id",
            "phase5i_run",
            "phase5h_source_run",
            "source_sales_invoice",
            "payment_entry",
        ],
        "executed_on desc, creation desc",
    )


def evaluate_config(items):
    config = config_state()
    if config["production_mode"]:
        add_item(items, "Blocker", "Critical", "Site Config", "production_mode", "Production mode", "Production mode is enabled.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "production_mode", "Production mode", "Production mode remains disabled.")
    if config["live_pe_enabled"]:
        add_item(items, "Blocker", "Critical", "Site Config", "live_pe_enabled", "Live PE posting config", "Live PE posting config is enabled.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "live_pe_enabled", "Live PE posting config", "Live Payment Entry posting remains disabled globally.")
    if config["sandbox_enabled"]:
        add_item(items, "Pass", "Low", "Site Config", "sandbox_enabled", "Sandbox config", "Sandbox config remains enabled.")
    else:
        add_item(items, "Warning", "Medium", "Site Config", "sandbox_enabled", "Sandbox config", "Sandbox config is not enabled.")
    return config


def evaluate_phase_evidence(items):
    rollback = latest_full_rollback()
    if not rollback:
        add_item(items, "Blocker", "Critical", "Phase Evidence", "phase5j_full_rollback", "Phase 5J full rollback", "No completed full rollback run found.")
        return None, None, None, None, None

    add_item(items, "Pass", "Low", "Phase Evidence", "phase5j_full_rollback", "Phase 5J full rollback", f"Full rollback found: {rollback.rollback_run_id}.", None, "NDIS PE Smoke Rollback Run", rollback.name)

    phase5i = frappe.get_doc("NDIS PE One Submitted Smoke Run", rollback.phase5i_run) if rollback.phase5i_run and frappe.db.exists("NDIS PE One Submitted Smoke Run", rollback.phase5i_run) else None
    phase5h = frappe.get_doc("NDIS PE Smoke Invoice Source Run", rollback.phase5h_source_run) if rollback.phase5h_source_run and frappe.db.exists("NDIS PE Smoke Invoice Source Run", rollback.phase5h_source_run) else None
    pe = frappe.get_doc("Payment Entry", rollback.payment_entry) if rollback.payment_entry and frappe.db.exists("Payment Entry", rollback.payment_entry) else None
    si = frappe.get_doc("Sales Invoice", rollback.source_sales_invoice) if rollback.source_sales_invoice and frappe.db.exists("Sales Invoice", rollback.source_sales_invoice) else None

    if phase5i and phase5i.status == "Payment Cancelled":
        add_item(items, "Pass", "Low", "Phase Evidence", "phase5i_payment_cancelled", "Phase 5I run status", "Phase 5I run is marked Payment Cancelled.", None, "NDIS PE One Submitted Smoke Run", phase5i.name)
    else:
        add_item(items, "Blocker", "Critical", "Phase Evidence", "phase5i_payment_cancelled", "Phase 5I run status", "Phase 5I run is missing or not Payment Cancelled.")

    if phase5h and phase5h.status == "Source Cancelled":
        add_item(items, "Pass", "Low", "Phase Evidence", "phase5h_source_cancelled", "Phase 5H source run status", "Phase 5H source run is marked Source Cancelled.", None, "NDIS PE Smoke Invoice Source Run", phase5h.name)
    else:
        add_item(items, "Blocker", "Critical", "Phase Evidence", "phase5h_source_cancelled", "Phase 5H source run status", "Phase 5H source run is missing or not Source Cancelled.")

    return rollback, phase5i, phase5h, pe, si


def evaluate_payment_entry(items, pe):
    if not pe:
        add_item(items, "Blocker", "Critical", "Payment Entry Evidence", "pe_exists", "Payment Entry exists", "Tagged Phase 5I Payment Entry is missing.")
        return
    if not int(getattr(pe, "custom_ndis_pe_one_submitted_smoke", 0) or 0):
        add_item(items, "Blocker", "Critical", "Payment Entry Evidence", "pe_tag", "Phase 5I PE tag", "Payment Entry is not tagged as Phase 5I smoke.")
    else:
        add_item(items, "Pass", "Low", "Payment Entry Evidence", "pe_tag", "Phase 5I PE tag", "Payment Entry is tagged as Phase 5I smoke.")
    if pe.docstatus != 2:
        add_item(items, "Blocker", "Critical", "Payment Entry Evidence", "pe_docstatus", "Payment Entry docstatus", f"Payment Entry docstatus is {pe.docstatus}; expected 2.")
    else:
        add_item(items, "Pass", "Low", "Payment Entry Evidence", "pe_docstatus", "Payment Entry docstatus", "Payment Entry is cancelled.")

    pe_gl_count = gl_count("Payment Entry", pe.name)
    pe_gl_net = gl_net("Payment Entry", pe.name)
    if pe_gl_count <= 0:
        add_item(items, "Blocker", "Critical", "Payment Entry GL", "pe_gl_count", "Payment Entry GL count", "No Payment Entry GL found.")
    elif abs(pe_gl_net) > 0.0001:
        add_item(items, "Blocker", "Critical", "Payment Entry GL", "pe_gl_net", "Payment Entry GL net", f"Payment Entry GL net is {pe_gl_net}; expected 0.00.")
    else:
        add_item(items, "Pass", "Low", "Payment Entry GL", "pe_gl", "Payment Entry GL evidence", f"Payment Entry GL has {pe_gl_count} rows and nets to 0.00.")


def evaluate_sales_invoice(items, si):
    if not si:
        add_item(items, "Blocker", "Critical", "Sales Invoice Evidence", "si_exists", "Source Sales Invoice exists", "Phase 5H source Sales Invoice is missing.")
        return
    if not int(getattr(si, "custom_ndis_pe_smoke_source_invoice", 0) or 0):
        add_item(items, "Blocker", "Critical", "Sales Invoice Evidence", "si_tag", "Phase 5H source tag", "Sales Invoice is not tagged as Phase 5H source.")
    else:
        add_item(items, "Pass", "Low", "Sales Invoice Evidence", "si_tag", "Phase 5H source tag", "Sales Invoice is tagged as Phase 5H source.")
    if si.docstatus != 2:
        add_item(items, "Blocker", "Critical", "Sales Invoice Evidence", "si_docstatus", "Source invoice docstatus", f"Sales Invoice docstatus is {si.docstatus}; expected 2.")
    else:
        add_item(items, "Pass", "Low", "Sales Invoice Evidence", "si_docstatus", "Source invoice docstatus", "Source Sales Invoice is cancelled.")
    if not int(getattr(si, "custom_ndis_pe_smoke_source_cancelled", 0) or 0):
        add_item(items, "Blocker", "Critical", "Sales Invoice Evidence", "si_cancel_flag", "Source invoice cancelled flag", "Source invoice cancelled flag is not set.")
    else:
        add_item(items, "Pass", "Low", "Sales Invoice Evidence", "si_cancel_flag", "Source invoice cancelled flag", "Source invoice cancelled flag is set.")

    si_gl_count = gl_count("Sales Invoice", si.name)
    si_gl_net = gl_net("Sales Invoice", si.name)
    if si_gl_count <= 0:
        add_item(items, "Blocker", "Critical", "Sales Invoice GL", "si_gl_count", "Sales Invoice GL count", "No Sales Invoice GL found.")
    elif abs(si_gl_net) > 0.0001:
        add_item(items, "Blocker", "Critical", "Sales Invoice GL", "si_gl_net", "Sales Invoice GL net", f"Sales Invoice GL net is {si_gl_net}; expected 0.00.")
    else:
        add_item(items, "Pass", "Low", "Sales Invoice GL", "si_gl", "Sales Invoice GL evidence", f"Sales Invoice GL has {si_gl_count} rows and nets to 0.00.")


def evidence_counts():
    return {
        "submitted_phase5i_pe_count": count_dt("Payment Entry", {"custom_ndis_pe_one_submitted_smoke": 1, "docstatus": 1}),
        "cancelled_phase5i_pe_count": count_dt("Payment Entry", {"custom_ndis_pe_one_submitted_smoke": 1, "docstatus": 2}),
        "active_phase5h_source_invoice_count": count_dt("Sales Invoice", {"custom_ndis_pe_smoke_source_invoice": 1, "docstatus": 1}),
        "cancelled_phase5h_source_invoice_count": count_dt("Sales Invoice", {"custom_ndis_pe_smoke_source_invoice": 1, "docstatus": 2}),
        "fully_rolled_back_count": count_dt("NDIS PE Smoke Rollback Run", {"status": "Fully Rolled Back"}),
    }


def evaluate_counts(items):
    counts = evidence_counts()
    checks = [
        ("submitted_phase5i_pe_count", counts["submitted_phase5i_pe_count"] == 0, "Submitted Phase 5I PE count", "Zero submitted Phase 5I PE remains.", f"{counts['submitted_phase5i_pe_count']} submitted Phase 5I PE exists."),
        ("cancelled_phase5i_pe_count", counts["cancelled_phase5i_pe_count"] >= 1, "Cancelled Phase 5I PE count", f"{counts['cancelled_phase5i_pe_count']} cancelled Phase 5I PE found.", "No cancelled Phase 5I PE found."),
        ("active_phase5h_source_invoice_count", counts["active_phase5h_source_invoice_count"] == 0, "Active Phase 5H source invoice count", "Zero active source invoice remains.", f"{counts['active_phase5h_source_invoice_count']} active source invoice exists."),
        ("cancelled_phase5h_source_invoice_count", counts["cancelled_phase5h_source_invoice_count"] >= 1, "Cancelled Phase 5H source invoice count", f"{counts['cancelled_phase5h_source_invoice_count']} cancelled source invoice found.", "No cancelled Phase 5H source invoice found."),
        ("fully_rolled_back_count", counts["fully_rolled_back_count"] >= 1, "Fully rolled back count", f"{counts['fully_rolled_back_count']} full rollback run found.", "No full rollback run found."),
    ]
    for key, ok, label, pass_detail, fail_detail in checks:
        add_item(
            items,
            "Pass" if ok else "Blocker",
            "Low" if ok else "Critical",
            "Cycle Counts",
            key,
            label,
            pass_detail if ok else fail_detail,
        )
    return counts


def guardrails():
    return {
        "new_payment_entry_created": 0,
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
        "live_enabled_policy_count": count_dt("NDIS PE Production Posting Policy", {"production_posting_enabled": 1}),
    }


def evaluate_guardrails(items):
    values = guardrails()
    checks = [
        ("new_payment_entry_created", values["new_payment_entry_created"], "New Payment Entry created"),
        ("submitted_journal_entry_count_today", values["submitted_journal_entry_count_today"], "Submitted Journal Entry today"),
        ("purchase_invoice_count_today", values["purchase_invoice_count_today"], "Purchase Invoice today"),
        ("live_enabled_policy_count", values["live_enabled_policy_count"], "Live-enabled policy count"),
    ]
    for key, value, label in checks:
        if value:
            add_item(items, "Blocker", "Critical", "Guardrail", key, label, f"{value} record(s) found.")
        else:
            add_item(items, "Pass", "Low", "Guardrail", key, label, "Zero.")
    return values


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


def freeze_status(score, blockers, warnings, frozen):
    if blockers:
        return "Blocked"
    if frozen:
        return "Frozen"
    if warnings:
        return "Ready With Warnings"
    if score >= 95:
        return "Ready To Freeze"
    return "Needs Review"


def create_freeze_items(doc, items):
    for item in items:
        row = frappe.new_doc(ITEM_DOCTYPE)
        row.completion_freeze = doc.name
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


def evaluate_freeze_inputs(acknowledgement=None, dry_run=1):
    items = []
    config = evaluate_config(items)
    rollback, phase5i, phase5h, pe, si = evaluate_phase_evidence(items)
    evaluate_payment_entry(items, pe)
    evaluate_sales_invoice(items, si)
    counts = evaluate_counts(items)
    guard = evaluate_guardrails(items)

    ack_ok = acknowledgement == FREEZE_ACK
    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "freeze_ack", "Freeze acknowledgement", "Exact acknowledgement supplied.")
    elif int(dry_run or 0):
        add_item(items, "Info", "Low", "Acknowledgement", "freeze_ack", "Freeze acknowledgement", f"Dry-run preview only. Required for freeze: {FREEZE_ACK}")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "freeze_ack", "Freeze acknowledgement", f"Required acknowledgement not supplied. Required: {FREEZE_ACK}", "Provide exact acknowledgement to freeze the completion evidence.")

    summary = summarise_items(items)
    score = calculate_score(summary["blocker_count"], summary["warning_count"])
    frozen_allowed = int(ack_ok and summary["blocker_count"] == 0)

    return {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Frozen" if frozen_allowed else ("Blocked" if summary["blocker_count"] else ("Previewed" if int(dry_run or 0) else "Needs Review")),
        "freeze_status": freeze_status(score, summary["blocker_count"], summary["warning_count"], frozen_allowed),
        "freeze_score": score,
        "completion_freeze_allowed": frozen_allowed,
        "ready_for_next_phase": frozen_allowed,
        "phase5j_rollback_run": rollback.name if rollback else None,
        "phase5i_run": phase5i.name if phase5i else None,
        "phase5h_source_run": phase5h.name if phase5h else None,
        "payment_entry": pe.name if pe else None,
        "source_sales_invoice": si.name if si else None,
        "payment_entry_docstatus": pe.docstatus if pe else None,
        "source_invoice_docstatus": si.docstatus if si else None,
        "source_invoice_cancelled_flag": int(getattr(si, "custom_ndis_pe_smoke_source_cancelled", 0) or 0) if si else 0,
        "source_invoice_outstanding": flt(si.outstanding_amount) if si else 0,
        "payment_entry_gl_count": gl_count("Payment Entry", pe.name) if pe else 0,
        "payment_entry_gl_net": gl_net("Payment Entry", pe.name) if pe else 0,
        "sales_invoice_gl_count": gl_count("Sales Invoice", si.name) if si else 0,
        "sales_invoice_gl_net": gl_net("Sales Invoice", si.name) if si else 0,
        "counts": counts,
        "guardrails": guard,
        "config": config,
        "required_acknowledgement": FREEZE_ACK,
        "acknowledgement_ok": ack_ok,
        "summary": summary,
        "items": items,
        "note": "Phase 5K is read-only evidence freeze. No accounting document is created, submitted, cancelled, or modified.",
    }


@frappe.whitelist()
def run_pe_live_smoke_completion_freeze(acknowledgement=None, dry_run=1, notes=None):
    assert_action("run_pe_live_smoke_completion_freeze")
    result = evaluate_freeze_inputs(acknowledgement=acknowledgement, dry_run=dry_run)
    if int(dry_run or 0):
        return result

    doc = frappe.new_doc(FREEZE_DOCTYPE)
    doc.completion_freeze_id = make_freeze_id()
    doc.status = result["status"]
    doc.freeze_type = "Payment Entry Live Smoke Completion"
    doc.completion_freeze_allowed = result["completion_freeze_allowed"]
    doc.ready_for_next_phase = result["ready_for_next_phase"]
    doc.phase5h_source_run = result["phase5h_source_run"]
    doc.phase5i_run = result["phase5i_run"]
    doc.phase5j_rollback_run = result["phase5j_rollback_run"]
    doc.source_sales_invoice = result["source_sales_invoice"]
    doc.payment_entry = result["payment_entry"]
    doc.payment_entry_docstatus = result["payment_entry_docstatus"] or 0
    doc.source_invoice_docstatus = result["source_invoice_docstatus"] or 0
    doc.source_invoice_cancelled_flag = result["source_invoice_cancelled_flag"]
    doc.source_invoice_outstanding = result["source_invoice_outstanding"]
    doc.payment_entry_gl_count = result["payment_entry_gl_count"]
    doc.payment_entry_gl_net = result["payment_entry_gl_net"]
    doc.sales_invoice_gl_count = result["sales_invoice_gl_count"]
    doc.sales_invoice_gl_net = result["sales_invoice_gl_net"]
    for key, value in result["counts"].items():
        setattr(doc, key, value)
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = result["config"]["sandbox_enabled"]
    doc.production_mode_detected = result["config"]["production_mode"]
    doc.live_payment_entry_posting_config = result["config"]["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.freeze_score = result["freeze_score"]
    doc.freeze_status = result["freeze_status"]
    doc.blocker_count = result["summary"]["blocker_count"]
    doc.warning_count = result["summary"]["warning_count"]
    doc.pass_count = result["summary"]["pass_count"]
    doc.info_count = result["summary"]["info_count"]
    doc.item_count = result["summary"]["item_count"]
    doc.new_payment_entry_created = 0
    doc.submitted_journal_entry_count_today = result["guardrails"]["submitted_journal_entry_count_today"]
    doc.purchase_invoice_count_today = result["guardrails"]["purchase_invoice_count_today"]
    doc.live_enabled_policy_count = result["guardrails"]["live_enabled_policy_count"]
    doc.required_acknowledgement = FREEZE_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(result["acknowledgement_ok"])
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    result["created"] = True
    result["completion_freeze"] = doc.name
    result["completion_freeze_id"] = doc.completion_freeze_id
    doc.summary_json = safe_json(result)
    doc.save(ignore_permissions=True)
    create_freeze_items(doc, result["items"])
    frappe.db.commit()
    return result


@frappe.whitelist()
def cancel_pe_live_smoke_completion_freeze(completion_freeze, reason=None):
    assert_action("cancel_pe_live_smoke_completion_freeze")
    if not frappe.db.exists(FREEZE_DOCTYPE, completion_freeze):
        frappe.throw(_("Completion freeze not found: {0}").format(completion_freeze))
    doc = frappe.get_doc(FREEZE_DOCTYPE, completion_freeze)
    if doc.status == "Frozen":
        frappe.throw(_("Frozen completion evidence cannot be cancelled. Create a new superseding freeze if required."))
    frappe.db.set_value(
        FREEZE_DOCTYPE,
        completion_freeze,
        {
            "status": "Cancelled",
            "completion_freeze_allowed": 0,
            "ready_for_next_phase": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 5K completion freeze cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(
        f"""
        UPDATE `tab{ITEM_DOCTYPE}`
        SET status = 'Cancelled'
        WHERE completion_freeze = %(completion_freeze)s
        """,
        {"completion_freeze": completion_freeze},
    )
    frappe.db.commit()
    return {
        "completion_freeze": completion_freeze,
        "status": "Cancelled",
        "note": "Completion freeze audit record cancelled only. No accounting movement occurred.",
    }


@frappe.whitelist()
def quick_pe_live_smoke_completion_freeze_summary(limit=20):
    freezes = frappe.get_all(
        FREEZE_DOCTYPE,
        fields=[
            "name",
            "completion_freeze_id",
            "status",
            "freeze_status",
            "freeze_score",
            "completion_freeze_allowed",
            "ready_for_next_phase",
            "phase5j_rollback_run",
            "payment_entry",
            "source_sales_invoice",
            "payment_entry_docstatus",
            "source_invoice_docstatus",
            "payment_entry_gl_count",
            "payment_entry_gl_net",
            "sales_invoice_gl_count",
            "sales_invoice_gl_net",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        ITEM_DOCTYPE,
        fields=[
            "name",
            "completion_freeze",
            "status",
            "severity",
            "category",
            "check_label",
            "detail",
            "recommendation",
            "source_doctype",
            "source_name",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {
        "freezes": freezes,
        "items": items,
        "required_acknowledgement": FREEZE_ACK,
        "config": config_state(),
        "counts": evidence_counts(),
        "guardrails": guardrails(),
        "note": "Phase 5K summary only. No accounting movement is performed.",
    }


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
    columns = [
        {"fieldname": "completion_freeze", "label": _("Completion Freeze"), "fieldtype": "Link", "options": FREEZE_DOCTYPE, "width": 220},
        {"fieldname": "completion_freeze_id", "label": _("Freeze ID"), "fieldtype": "Data", "width": 360},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "freeze_status", "label": _("Freeze Status"), "fieldtype": "Data", "width": 180},
        {"fieldname": "completion_freeze_allowed", "label": _("Freeze Allowed"), "fieldtype": "Check", "width": 110},
        {"fieldname": "ready_for_next_phase", "label": _("Ready Next"), "fieldtype": "Check", "width": 100},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 170},
        {"fieldname": "source_sales_invoice", "label": _("Source SI"), "fieldtype": "Link", "options": "Sales Invoice", "width": 170},
        {"fieldname": "payment_entry_gl_count", "label": _("PE GL Count"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_gl_net", "label": _("PE GL Net"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "sales_invoice_gl_count", "label": _("SI GL Count"), "fieldtype": "Int", "width": 110},
        {"fieldname": "sales_invoice_gl_net", "label": _("SI GL Net"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            f.name AS completion_freeze,
            f.completion_freeze_id,
            f.status,
            f.freeze_status,
            f.completion_freeze_allowed,
            f.ready_for_next_phase,
            f.payment_entry,
            f.source_sales_invoice,
            f.payment_entry_gl_count,
            f.payment_entry_gl_net,
            f.sales_invoice_gl_count,
            f.sales_invoice_gl_net,
            f.checked_on,
            %(currency)s AS currency
        FROM `tab{FREEZE_DOCTYPE}` f
        {build_where(conditions)}
        ORDER BY f.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.completion_freeze_id for row in data[:20]],
            "datasets": [
                {"name": "Freeze Allowed", "values": [int(row.completion_freeze_allowed or 0) for row in data[:20]]},
                {"name": "Ready Next", "values": [int(row.ready_for_next_phase or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Freezes"), "datatype": "Int"},
        {"value": sum(int(row.completion_freeze_allowed or 0) for row in data), "indicator": "Green", "label": _("Frozen"), "datatype": "Int"},
        {"value": sum(int(row.ready_for_next_phase or 0) for row in data), "indicator": "Green", "label": _("Ready For Next Phase"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_exception_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    if filters.get("completion_freeze"):
        conditions.append("i.completion_freeze = %(completion_freeze)s")
        params["completion_freeze"] = filters.completion_freeze
    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.status
    if filters.get("severity"):
        conditions.append("i.severity = %(severity)s")
        params["severity"] = filters.severity
    if filters.get("category"):
        conditions.append("i.category = %(category)s")
        params["category"] = filters.category
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": ITEM_DOCTYPE, "width": 220},
        {"fieldname": "completion_freeze", "label": _("Completion Freeze"), "fieldtype": "Link", "options": FREEZE_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 180},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 320},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 460},
        {"fieldname": "recommendation", "label": _("Recommendation"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 180},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Data", "width": 220},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item,
            i.completion_freeze,
            i.status,
            i.severity,
            i.category,
            i.check_label,
            i.detail,
            i.recommendation,
            i.source_doctype,
            i.source_name,
            i.checked_on
        FROM `tab{ITEM_DOCTYPE}` i
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


def execute_gl_evidence_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = [
        """
        (
            gl.voucher_no IN (
                SELECT name FROM `tabPayment Entry`
                WHERE custom_ndis_pe_one_submitted_smoke = 1
            )
            OR gl.voucher_no IN (
                SELECT name FROM `tabSales Invoice`
                WHERE custom_ndis_pe_smoke_source_invoice = 1
            )
        )
        """
    ]
    params = {"currency": currency()}
    if filters.get("voucher_no"):
        conditions.append("gl.voucher_no = %(voucher_no)s")
        params["voucher_no"] = filters.voucher_no
    if filters.get("voucher_type"):
        conditions.append("gl.voucher_type = %(voucher_type)s")
        params["voucher_type"] = filters.voucher_type
    columns = [
        {"fieldname": "voucher_type", "label": _("Voucher Type"), "fieldtype": "Data", "width": 140},
        {"fieldname": "voucher_no", "label": _("Voucher No"), "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 180},
        {"fieldname": "gl_entry", "label": _("GL Entry"), "fieldtype": "Link", "options": "GL Entry", "width": 220},
        {"fieldname": "account", "label": _("Account"), "fieldtype": "Link", "options": "Account", "width": 240},
        {"fieldname": "debit", "label": _("Debit"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "credit", "label": _("Credit"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "is_cancelled", "label": _("Is Cancelled"), "fieldtype": "Check", "width": 100},
        {"fieldname": "posting_date", "label": _("Posting Date"), "fieldtype": "Date", "width": 110},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            gl.voucher_type,
            gl.voucher_no,
            gl.name AS gl_entry,
            gl.account,
            gl.debit,
            gl.credit,
            gl.is_cancelled,
            gl.posting_date,
            %(currency)s AS currency
        FROM `tabGL Entry` gl
        {build_where(conditions)}
        ORDER BY gl.voucher_type, gl.voucher_no, gl.creation ASC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": ["Debit", "Credit"],
            "datasets": [{
                "name": "GL",
                "values": [sum(flt(row.debit) for row in data), sum(flt(row.credit) for row in data)],
            }],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("GL Rows"), "datatype": "Int"},
        {"value": sum(flt(row.debit) for row in data), "indicator": "Green", "label": _("Debit"), "datatype": "Currency", "currency": currency()},
        {"value": sum(flt(row.credit) for row in data), "indicator": "Green", "label": _("Credit"), "datatype": "Currency", "currency": currency()},
        {"value": sum(flt(row.debit) - flt(row.credit) for row in data), "indicator": "Blue", "label": _("Net"), "datatype": "Currency", "currency": currency()},
    ]
    return columns, data, None, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
