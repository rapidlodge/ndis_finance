import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


POLICY_DOCTYPE = "NDIS Real Remittance Batch Posting Policy"
GATE_DOCTYPE = "NDIS Real Remittance Batch Design Gate"
ITEM_DOCTYPE = "NDIS Real Remittance Batch Design Gate Item"
DESIGN_ACK = "I_CONFIRM_PHASE7A_REAL_REMITTANCE_BATCH_DESIGN_GATE_NO_POSTING"


def make_design_gate_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-REAL-REMITTANCE-BATCH-DESIGN-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def sales_invoice_today_guardrail_count():
    if frappe.db.has_column("Sales Invoice", "custom_ndis_real_remittance_pe_harness_invoice"):
        return frappe.db.sql(
            """
            SELECT COUNT(*)
            FROM `tabSales Invoice`
            WHERE creation >= %(today)s
            AND IFNULL(custom_ndis_real_remittance_pe_harness_invoice, 0) = 0
            """,
            {"today": today()},
        )[0][0]
    return count_dt("Sales Invoice", {"creation": [">=", today()]})


def guardrails():
    return {
        "payment_entry_count": count_dt("Payment Entry"),
        "payment_entry_gl_count": count_dt("GL Entry", {"voucher_type": "Payment Entry"}),
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
        "sales_invoice_count_today": sales_invoice_today_guardrail_count(),
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
        "production_live_policy_count": count_dt("NDIS PE Production Posting Policy", {"production_posting_enabled": 1}),
    }


def latest_freeze():
    rows = frappe.get_all(
        "NDIS Real Remittance PE Evidence Freeze",
        filters={
            "status": "Frozen",
            "evidence_freeze_allowed": 1,
            "ready_for_next_phase": 1,
            "real_posting_allowed": 0,
        },
        fields=[
            "name",
            "freeze_id",
            "design_gate",
            "preview",
            "adapter_run",
            "activation_gate",
            "source_harness_run",
            "smoke_run",
            "rollback_run",
            "company",
            "phase6b_eligible_line_count",
            "phase6c_hard_blocked_line_count",
            "phase6d_ready_for_real_smoke",
            "phase6f_submitted_pe_count",
            "phase6g_cancelled_pe_count",
            "payment_entry_docstatus_after",
            "payment_entry_gl_count_after",
            "payment_entry_gl_net_after",
            "submitted_smoke_pe_count",
            "cancelled_smoke_pe_count",
            "ready_for_next_phase",
            "real_posting_allowed",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    return rows[0] if rows else None


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


def evaluate_config(items, config):
    if config["production_mode"]:
        add_item(items, "Blocker", "Critical", "Site Config", "production_mode", "Production mode", "Production mode is enabled.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "production_mode", "Production mode", "Production mode remains disabled.")

    if config["live_pe_enabled"]:
        add_item(items, "Blocker", "Critical", "Site Config", "live_pe_enabled", "Live PE posting config", "Live Payment Entry posting config is enabled.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "live_pe_enabled", "Live PE posting config", "Live Payment Entry posting remains disabled.")

    if config["sandbox_enabled"]:
        add_item(items, "Pass", "Low", "Site Config", "sandbox_enabled", "Sandbox config", "Sandbox config remains enabled.")
    else:
        add_item(items, "Warning", "Medium", "Site Config", "sandbox_enabled", "Sandbox config", "Sandbox config is not enabled.")


def evaluate_freeze(items, freeze):
    if not freeze:
        add_item(items, "Blocker", "Critical", "Phase 6H", "freeze_exists", "Phase 6H evidence freeze", "No valid Phase 6H evidence freeze found.", "Complete Phase 6H first.")
        return

    add_item(items, "Pass", "Low", "Phase 6H", "freeze_exists", "Phase 6H evidence freeze", f"Frozen evidence found: {freeze.freeze_id}.", None, "NDIS Real Remittance PE Evidence Freeze", freeze.name)

    if int(freeze.ready_for_next_phase or 0) == 1 and int(freeze.real_posting_allowed or 0) == 0:
        add_item(items, "Pass", "Low", "Phase 6H", "freeze_ready", "Freeze ready for next phase", "Freeze is ready and real posting remains disabled.")
    else:
        add_item(items, "Blocker", "Critical", "Phase 6H", "freeze_ready", "Freeze ready for next phase", "Freeze is not ready or real posting is enabled.")

    if int(freeze.submitted_smoke_pe_count or 0) == 0 and int(freeze.cancelled_smoke_pe_count or 0) >= 1:
        add_item(items, "Pass", "Low", "Phase 6H", "smoke_rolled_back", "Smoke PE rolled back", "Submitted smoke PE count is 0 and cancelled smoke PE evidence exists.")
    else:
        add_item(items, "Blocker", "Critical", "Phase 6H", "smoke_rolled_back", "Smoke PE rolled back", "Smoke PE rollback evidence is invalid.")

    if int(freeze.payment_entry_docstatus_after or 0) == 2:
        add_item(items, "Pass", "Low", "Payment Entry", "pe_cancelled", "Controlled PE cancelled", "Controlled smoke Payment Entry docstatus is 2.")
    else:
        add_item(items, "Blocker", "Critical", "Payment Entry", "pe_cancelled", "Controlled PE cancelled", "Controlled smoke Payment Entry is not cancelled.")


def evaluate_policy_register(items):
    policy_count = count_dt(POLICY_DOCTYPE)
    active_policy_count = count_dt(POLICY_DOCTYPE, {"policy_status": "Active"})
    live_enabled_policy_count = count_dt(POLICY_DOCTYPE, {"batch_live_enabled": 1})

    if policy_count >= 9:
        add_item(items, "Pass", "Low", "Policy Register", "policy_count", "Batch policies seeded", f"{policy_count} policies found.")
    else:
        add_item(items, "Blocker", "Critical", "Policy Register", "policy_count", "Batch policies seeded", f"Only {policy_count} policies found.")

    if active_policy_count >= 9:
        add_item(items, "Pass", "Low", "Policy Register", "active_policy_count", "Active batch policies", f"{active_policy_count} active policies found.")
    else:
        add_item(items, "Blocker", "Critical", "Policy Register", "active_policy_count", "Active batch policies", f"Only {active_policy_count} active policies found.")

    if live_enabled_policy_count == 0:
        add_item(items, "Pass", "Low", "Policy Register", "live_policy_zero", "Live-enabled batch policies", "Zero live-enabled batch policies.")
    else:
        add_item(items, "Blocker", "Critical", "Policy Register", "live_policy_zero", "Live-enabled batch policies", f"{live_enabled_policy_count} live-enabled batch policy record(s) found.")

    return {
        "policy_count": policy_count,
        "active_policy_count": active_policy_count,
        "live_enabled_policy_count": live_enabled_policy_count,
    }


def evaluate_batch_caps(items, max_batch_lines, max_batch_amount):
    if int(max_batch_lines or 0) <= 0:
        add_item(items, "Blocker", "Critical", "Batch Cap", "max_batch_lines_positive", "Max batch lines", "Max batch lines must be positive.")
    elif int(max_batch_lines or 0) <= 3:
        add_item(items, "Pass", "Low", "Batch Cap", "max_batch_lines", "Max batch lines", f"Max batch lines capped at {max_batch_lines}.")
    else:
        add_item(items, "Blocker", "Critical", "Batch Cap", "max_batch_lines", "Max batch lines", f"Max batch lines {max_batch_lines} exceeds Phase 7A cap of 3.")

    if flt(max_batch_amount or 0) <= 0:
        add_item(items, "Blocker", "Critical", "Batch Cap", "max_batch_amount_positive", "Max batch amount", "Max batch amount must be positive.")
    elif flt(max_batch_amount or 0) <= 3:
        add_item(items, "Pass", "Low", "Batch Cap", "max_batch_amount", "Max batch amount", f"Max batch amount capped at {flt(max_batch_amount, 2)}.")
    else:
        add_item(items, "Blocker", "Critical", "Batch Cap", "max_batch_amount", "Max batch amount", f"Max batch amount {flt(max_batch_amount, 2)} exceeds Phase 7A cap of 3.00.")


def evaluate_guardrails(items, guard):
    if guard["submitted_journal_entry_count_today"] == 0:
        add_item(items, "Pass", "Low", "Guardrail", "submitted_je_today", "Submitted JE today", "Zero.")
    else:
        add_item(items, "Blocker", "Critical", "Guardrail", "submitted_je_today", "Submitted JE today", f"{guard['submitted_journal_entry_count_today']} submitted Journal Entry record(s) found today.")

    if guard["sales_invoice_count_today"] == 0:
        add_item(items, "Pass", "Low", "Guardrail", "sales_invoice_today", "Non-harness Sales Invoice today", "Zero.")
    else:
        add_item(items, "Blocker", "Critical", "Guardrail", "sales_invoice_today", "Non-harness Sales Invoice today", f"{guard['sales_invoice_count_today']} non-harness Sales Invoice record(s) found today.")

    if guard["purchase_invoice_count_today"] == 0:
        add_item(items, "Pass", "Low", "Guardrail", "purchase_invoice_today", "Purchase Invoice today", "Zero.")
    else:
        add_item(items, "Blocker", "Critical", "Guardrail", "purchase_invoice_today", "Purchase Invoice today", f"{guard['purchase_invoice_count_today']} Purchase Invoice record(s) found today.")

    if guard["production_live_policy_count"] == 0:
        add_item(items, "Pass", "Low", "Guardrail", "production_live_policy", "Production PE live policies", "Zero.")
    else:
        add_item(items, "Blocker", "Critical", "Guardrail", "production_live_policy", "Production PE live policies", f"{guard['production_live_policy_count']} live-enabled production policy record(s) found.")


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


def create_gate_items(doc, items):
    for item in items:
        row = frappe.new_doc(ITEM_DOCTYPE)
        row.design_gate = doc.name
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
def run_real_remittance_batch_design_gate(max_batch_lines=3, max_batch_amount=3, dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_real_remittance_batch_design_gate")
    max_batch_lines = int(max_batch_lines or 3)
    max_batch_amount = flt(max_batch_amount or 3)

    config = config_state()
    guard_before = guardrails()
    freeze = latest_freeze()
    items = []
    evaluate_config(items, config)
    evaluate_freeze(items, freeze)
    policy_counts = evaluate_policy_register(items)
    evaluate_batch_caps(items, max_batch_lines, max_batch_amount)
    evaluate_guardrails(items, guard_before)

    ack_ok = acknowledgement == DESIGN_ACK
    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "design_ack", "Design acknowledgement", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "design_ack", "Design acknowledgement", f"Required acknowledgement not supplied. Required: {DESIGN_ACK}", "Provide exact acknowledgement to approve Phase 7A design gate.")

    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    design_approved = int(ack_ok and item_summary["blocker_count"] == 0)
    status = "Approved" if design_approved else ("Blocked" if item_summary["blocker_count"] else "Needs Review")
    design_status = "Approved For Batch Preview" if design_approved else ("Blocked" if item_summary["blocker_count"] else "Needs Review")

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": status,
        "design_status": design_status,
        "design_score": score,
        "design_approved_for_preview_phase": design_approved,
        "ready_for_batch_preview": design_approved,
        "batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "evidence_freeze": freeze.name if freeze else None,
        "rollback_run": freeze.rollback_run if freeze else None,
        "smoke_run": freeze.smoke_run if freeze else None,
        "source_harness_run": freeze.source_harness_run if freeze else None,
        "activation_gate": freeze.activation_gate if freeze else None,
        "adapter_run": freeze.adapter_run if freeze else None,
        "preview": freeze.preview if freeze else None,
        "company": freeze.company if freeze else None,
        "max_batch_lines": max_batch_lines,
        "max_batch_amount": max_batch_amount,
        "allowed_outcomes": "Paid, Short Paid",
        "excluded_outcomes": "Rejected, Unmatched, Duplicate, Overpayment, Cross Company",
        "policy_counts": policy_counts,
        "phase6h_ready_for_next_phase": int(freeze.ready_for_next_phase or 0) if freeze else 0,
        "phase6h_real_posting_allowed": int(freeze.real_posting_allowed or 0) if freeze else 0,
        "items": items,
        "summary": item_summary,
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": DESIGN_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 7A is a design gate only. It creates no Payment Entry, GL Entry, Sales Invoice, Purchase Invoice, or external movement.",
    }

    if int(dry_run or 0):
        return result

    doc = frappe.new_doc(GATE_DOCTYPE)
    doc.design_gate_id = make_design_gate_id()
    doc.status = status
    doc.gate_type = "Real Remittance Batch Posting Design"
    doc.design_approved_for_preview_phase = design_approved
    doc.ready_for_batch_preview = design_approved
    doc.batch_posting_allowed = 0
    doc.real_posting_allowed = 0
    doc.evidence_freeze = result["evidence_freeze"]
    doc.rollback_run = result["rollback_run"]
    doc.smoke_run = result["smoke_run"]
    doc.source_harness_run = result["source_harness_run"]
    doc.activation_gate = result["activation_gate"]
    doc.adapter_run = result["adapter_run"]
    doc.preview = result["preview"]
    doc.company = result["company"]
    doc.allowed_outcomes = result["allowed_outcomes"]
    doc.excluded_outcomes = result["excluded_outcomes"]
    doc.max_batch_lines = max_batch_lines
    doc.max_batch_amount = max_batch_amount
    doc.first_batch_only = 1
    doc.requires_separate_activation_gate = 1
    doc.policy_count = policy_counts["policy_count"]
    doc.active_policy_count = policy_counts["active_policy_count"]
    doc.live_enabled_policy_count = policy_counts["live_enabled_policy_count"]
    doc.phase6h_ready_for_next_phase = result["phase6h_ready_for_next_phase"]
    doc.phase6h_real_posting_allowed = result["phase6h_real_posting_allowed"]
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.design_score = score
    doc.design_status = design_status
    doc.blocker_count = item_summary["blocker_count"]
    doc.warning_count = item_summary["warning_count"]
    doc.pass_count = item_summary["pass_count"]
    doc.info_count = item_summary["info_count"]
    doc.item_count = item_summary["item_count"]
    doc.payment_entry_count_before = guard_before["payment_entry_count"]
    doc.payment_entry_count_after = guardrails()["payment_entry_count"]
    doc.payment_entry_gl_count_before = guard_before["payment_entry_gl_count"]
    doc.payment_entry_gl_count_after = guardrails()["payment_entry_gl_count"]
    doc.submitted_journal_entry_count_today = guard_before["submitted_journal_entry_count_today"]
    doc.sales_invoice_count_today = guard_before["sales_invoice_count_today"]
    doc.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
    doc.required_acknowledgement = DESIGN_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_gate_items(doc, items)

    guard_after = guardrails()
    frappe.db.set_value(
        GATE_DOCTYPE,
        doc.name,
        {
            "payment_entry_count_after": guard_after["payment_entry_count"],
            "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
            "summary_json": safe_json({**result, "guardrails_after": guard_after}),
        },
        update_modified=False,
    )
    frappe.db.commit()

    result["created"] = True
    result["design_gate"] = doc.name
    result["design_gate_id"] = doc.design_gate_id
    result["guardrails_after"] = guard_after
    return result


@frappe.whitelist()
def cancel_real_remittance_batch_design_gate(design_gate, reason=None):
    assert_action("cancel_real_remittance_batch_design_gate")
    if not frappe.db.exists(GATE_DOCTYPE, design_gate):
        frappe.throw(_("Design gate not found: {0}").format(design_gate))
    doc = frappe.get_doc(GATE_DOCTYPE, design_gate)
    if doc.status == "Cancelled":
        return {"design_gate": design_gate, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.ready_for_batch_preview or 0):
        frappe.throw(_("Cannot cancel an approved batch design gate. Create a superseding gate instead."))

    frappe.db.set_value(
        GATE_DOCTYPE,
        design_gate,
        {
            "status": "Cancelled",
            "design_approved_for_preview_phase": 0,
            "ready_for_batch_preview": 0,
            "batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 7A design gate cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{ITEM_DOCTYPE}` SET status = 'Cancelled' WHERE design_gate = %(design_gate)s", {"design_gate": design_gate})
    frappe.db.commit()
    return {"design_gate": design_gate, "status": "Cancelled", "note": "Batch design gate audit record cancelled only. No accounting movement occurred."}


@frappe.whitelist()
def quick_real_remittance_batch_design_gate_summary(limit=20):
    gates = frappe.get_all(
        GATE_DOCTYPE,
        fields=[
            "name",
            "design_gate_id",
            "status",
            "design_status",
            "design_score",
            "design_approved_for_preview_phase",
            "ready_for_batch_preview",
            "batch_posting_allowed",
            "real_posting_allowed",
            "evidence_freeze",
            "company",
            "max_batch_lines",
            "max_batch_amount",
            "policy_count",
            "active_policy_count",
            "live_enabled_policy_count",
            "payment_entry_count_before",
            "payment_entry_count_after",
            "payment_entry_gl_count_before",
            "payment_entry_gl_count_after",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(ITEM_DOCTYPE, fields=["name", "design_gate", "status", "severity", "category", "check_label", "detail", "recommendation", "source_doctype", "source_name"], order_by="creation desc", limit=int(limit or 20))
    policies = frappe.get_all(POLICY_DOCTYPE, fields=["name", "policy_key", "policy_name", "policy_category", "policy_status", "severity", "batch_live_enabled", "max_batch_lines", "max_batch_amount"], order_by="policy_category asc, policy_key asc")
    return {
        "gates": gates,
        "items": items,
        "policies": policies,
        "required_acknowledgement": DESIGN_ACK,
        "guardrails": guardrails(),
        "config": config_state(),
        "note": "Phase 7A design summary. Batch posting and real posting remain disabled.",
    }


def execute_policy_register_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    for field in ["policy_status", "policy_category"]:
        if filters.get(field):
            conditions.append(f"p.{field} = %({field})s")
            params[field] = filters.get(field)
    if filters.get("batch_live_enabled") not in [None, ""]:
        conditions.append("p.batch_live_enabled = %(batch_live_enabled)s")
        params["batch_live_enabled"] = int(filters.get("batch_live_enabled"))

    columns = [
        {"fieldname": "policy", "label": _("Policy"), "fieldtype": "Link", "options": POLICY_DOCTYPE, "width": 260},
        {"fieldname": "policy_key", "label": _("Policy Key"), "fieldtype": "Data", "width": 260},
        {"fieldname": "policy_name", "label": _("Policy Name"), "fieldtype": "Data", "width": 300},
        {"fieldname": "policy_category", "label": _("Category"), "fieldtype": "Data", "width": 180},
        {"fieldname": "policy_status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "batch_live_enabled", "label": _("Batch Live Enabled"), "fieldtype": "Check", "width": 140},
        {"fieldname": "max_batch_lines", "label": _("Max Lines"), "fieldtype": "Int", "width": 100},
        {"fieldname": "max_batch_amount", "label": _("Max Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "rule_summary", "label": _("Rule Summary"), "fieldtype": "Small Text", "width": 520},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT p.name AS policy, p.policy_key, p.policy_name, p.policy_category, p.policy_status,
            p.severity, p.batch_live_enabled, p.max_batch_lines, p.max_batch_amount,
            p.rule_summary, %(currency)s AS currency
        FROM `tab{POLICY_DOCTYPE}` p
        {build_where(conditions)}
        ORDER BY p.policy_category, p.policy_key
        """,
        params,
        as_dict=True,
    )
    chart_map = {}
    for row in data:
        chart_map[row.policy_category or "Uncategorised"] = chart_map.get(row.policy_category or "Uncategorised", 0) + 1
    chart = {"data": {"labels": list(chart_map.keys()), "datasets": [{"name": "Policies", "values": list(chart_map.values())}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Policies"), "datatype": "Int"},
        {"value": len([row for row in data if row.policy_status == "Active"]), "indicator": "Green", "label": _("Active"), "datatype": "Int"},
        {"value": len([row for row in data if int(row.batch_live_enabled or 0)]), "indicator": "Red", "label": _("Live Enabled"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_design_gate_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("g.status = %(status)s")
        params["status"] = filters.status
    if filters.get("from_date"):
        conditions.append("DATE(g.checked_on) >= %(from_date)s")
        params["from_date"] = filters.from_date
    if filters.get("to_date"):
        conditions.append("DATE(g.checked_on) <= %(to_date)s")
        params["to_date"] = filters.to_date

    columns = [
        {"fieldname": "design_gate", "label": _("Design Gate"), "fieldtype": "Link", "options": GATE_DOCTYPE, "width": 220},
        {"fieldname": "design_gate_id", "label": _("Design Gate ID"), "fieldtype": "Data", "width": 360},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "design_status", "label": _("Design Status"), "fieldtype": "Data", "width": 220},
        {"fieldname": "design_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "ready_for_batch_preview", "label": _("Ready Preview"), "fieldtype": "Check", "width": 120},
        {"fieldname": "batch_posting_allowed", "label": _("Batch Posting Allowed"), "fieldtype": "Check", "width": 160},
        {"fieldname": "real_posting_allowed", "label": _("Real Posting Allowed"), "fieldtype": "Check", "width": 150},
        {"fieldname": "evidence_freeze", "label": _("Evidence Freeze"), "fieldtype": "Link", "options": "NDIS Real Remittance PE Evidence Freeze", "width": 220},
        {"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 220},
        {"fieldname": "max_batch_lines", "label": _("Max Lines"), "fieldtype": "Int", "width": 100},
        {"fieldname": "max_batch_amount", "label": _("Max Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "policy_count", "label": _("Policies"), "fieldtype": "Int", "width": 90},
        {"fieldname": "live_enabled_policy_count", "label": _("Live Policies"), "fieldtype": "Int", "width": 110},
        {"fieldname": "payment_entry_count_before", "label": _("PE Before"), "fieldtype": "Int", "width": 100},
        {"fieldname": "payment_entry_count_after", "label": _("PE After"), "fieldtype": "Int", "width": 100},
        {"fieldname": "payment_entry_gl_count_before", "label": _("PE GL Before"), "fieldtype": "Int", "width": 120},
        {"fieldname": "payment_entry_gl_count_after", "label": _("PE GL After"), "fieldtype": "Int", "width": 120},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]
    data = frappe.db.sql(
        f"""
        SELECT g.name AS design_gate, g.design_gate_id, g.status, g.design_status, g.design_score,
            g.ready_for_batch_preview, g.batch_posting_allowed, g.real_posting_allowed,
            g.evidence_freeze, g.company, g.max_batch_lines, g.max_batch_amount,
            g.policy_count, g.live_enabled_policy_count, g.payment_entry_count_before,
            g.payment_entry_count_after, g.payment_entry_gl_count_before,
            g.payment_entry_gl_count_after, g.checked_on, %(currency)s AS currency
        FROM `tab{GATE_DOCTYPE}` g
        {build_where(conditions)}
        ORDER BY g.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [row.design_gate_id for row in data[:20]],
            "datasets": [
                {"name": "Ready Preview", "values": [int(row.ready_for_batch_preview or 0) for row in data[:20]]},
                {"name": "Batch Posting Allowed", "values": [int(row.batch_posting_allowed or 0) for row in data[:20]]},
                {"name": "Real Posting Allowed", "values": [int(row.real_posting_allowed or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Design Gates"), "datatype": "Int"},
        {"value": sum(int(row.ready_for_batch_preview or 0) for row in data), "indicator": "Green", "label": _("Ready Preview"), "datatype": "Int"},
        {"value": sum(int(row.batch_posting_allowed or 0) for row in data), "indicator": "Red", "label": _("Batch Posting Allowed"), "datatype": "Int"},
        {"value": sum(int(row.real_posting_allowed or 0) for row in data), "indicator": "Red", "label": _("Real Posting Allowed"), "datatype": "Int"},
    ]
    return columns, data, None, chart, summary


def execute_exception_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}
    for field in ["design_gate", "status", "severity", "category"]:
        if filters.get(field):
            conditions.append(f"i.{field} = %({field})s")
            params[field] = filters.get(field)
    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": ITEM_DOCTYPE, "width": 220},
        {"fieldname": "design_gate", "label": _("Design Gate"), "fieldtype": "Link", "options": GATE_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 180},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 320},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 520},
        {"fieldname": "recommendation", "label": _("Recommendation"), "fieldtype": "Small Text", "width": 420},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 180},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Data", "width": 220},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    data = frappe.db.sql(
        f"""
        SELECT i.name AS item, i.design_gate, i.status, i.severity, i.category,
            i.check_label, i.detail, i.recommendation, i.source_doctype,
            i.source_name, i.checked_on
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


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
