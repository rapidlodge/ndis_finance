import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


POLICY_DESIGN_ACK = "I_CONFIRM_PHASE9B_DESIGN_LIMITED_PRODUCTION_BATCH_POLICY_NO_POSTING"


def make_policy_design_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-LIMITED-PROD-BATCH-POLICY-DESIGN-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def has_pe_phase8e_fields():
    return frappe.db.has_column("Payment Entry", "custom_ndis_controlled_prod_batch_smoke")


def submitted_phase8e_smoke_pe_count():
    if not has_pe_phase8e_fields():
        return 0

    return count_dt(
        "Payment Entry",
        {
            "docstatus": 1,
            "custom_ndis_controlled_prod_batch_smoke": 1,
        },
    )


def cancelled_phase8e_smoke_pe_count():
    if not has_pe_phase8e_fields():
        return 0

    return count_dt(
        "Payment Entry",
        {
            "docstatus": 2,
            "custom_ndis_controlled_prod_batch_smoke": 1,
        },
    )


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
        "submitted_journal_entry_count_today": count_dt("Journal Entry", {"creation": [">=", today()], "docstatus": 1}),
        "purchase_invoice_count_today": count_dt("Purchase Invoice", {"creation": [">=", today()]}),
        "production_batch_enabled_policy_count": count_dt("NDIS Controlled Production Batch Posting Policy", {"production_batch_enabled": 1}),
        "live_posting_allowed_policy_count": count_dt("NDIS Controlled Production Batch Posting Policy", {"live_posting_allowed": 1}),
        "submitted_phase8e_smoke_pe_count": submitted_phase8e_smoke_pe_count(),
        "cancelled_phase8e_smoke_pe_count": cancelled_phase8e_smoke_pe_count(),
    }


def latest_policy_review_gate():
    rows = frappe.get_all(
        "NDIS Controlled Production Batch Policy Review Gate",
        filters={
            "status": "Approved For Limited Policy Design",
            "policy_review_approved": 1,
            "ready_for_limited_policy_design": 1,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
        },
        fields=[
            "name",
            "policy_review_id",
            "phase8g_freeze",
            "rollback_run",
            "smoke_run",
            "activation_gate",
            "adapter_run",
            "preview",
            "design_gate",
            "phase7h_freeze",
            "source_run",
            "company",
            "customer",
            "payment_entry",
            "evidence_freeze_allowed",
            "rollback_completed",
            "controlled_payment_entry_cancelled",
            "payment_entry_docstatus_after_rollback",
            "payment_entry_amount",
            "invoice_count",
            "invoice_outstanding_after_rollback_total",
            "payment_entry_gl_count_after_rollback",
            "payment_entry_gl_net_after_rollback",
            "submitted_phase8e_smoke_pe_count",
            "cancelled_phase8e_smoke_pe_count",
            "recommended_policy_mode",
            "recommended_max_batch_lines",
            "recommended_max_batch_amount",
            "recommended_payment_entry_count",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )

    return rows[0] if rows else None


def existing_completed_design(policy_review_gate):
    rows = frappe.get_all(
        "NDIS Limited Production Batch Policy Design",
        filters={
            "policy_review_gate": policy_review_gate,
            "status": "Designed",
            "limited_policy_design_complete": 1,
            "ready_for_limited_policy_preview": 1,
        },
        fields=["name", "policy_design_id"],
        limit=1,
    )

    return rows[0] if rows else None


def pe_gl_count_net(payment_entry):
    rows = frappe.db.sql(
        """
        SELECT COUNT(*) AS gl_count, COALESCE(SUM(debit - credit), 0) AS gl_net
        FROM `tabGL Entry`
        WHERE voucher_type='Payment Entry'
        AND voucher_no=%(payment_entry)s
        """,
        {"payment_entry": payment_entry},
        as_dict=True,
    )

    return int(rows[0].gl_count or 0), flt(rows[0].gl_net or 0, 2)


def add_item(items, status, severity, category, check_key, check_label, detail):
    items.append(
        {
            "status": status,
            "severity": severity,
            "category": category,
            "check_key": check_key,
            "check_label": check_label,
            "detail": detail,
        }
    )


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


def validate_design_source(review, guard):
    issues = []

    if not review:
        issues.append("No approved Phase 9A policy review gate found.")
        return issues

    if existing_completed_design(review.name):
        issues.append("A completed Phase 9B limited policy design already exists for this Phase 9A review gate.")

    required_links = {
        "phase8g_freeze": review.phase8g_freeze,
        "rollback_run": review.rollback_run,
        "smoke_run": review.smoke_run,
        "activation_gate": review.activation_gate,
        "adapter_run": review.adapter_run,
        "preview": review.preview,
        "design_gate": review.design_gate,
    }

    for label, value in required_links.items():
        if not value:
            issues.append(f"Missing evidence link: {label}")

    if not int(review.evidence_freeze_allowed or 0):
        issues.append("Phase 8G evidence freeze is not allowed.")

    if not int(review.rollback_completed or 0):
        issues.append("Rollback completion evidence missing.")

    if not int(review.controlled_payment_entry_cancelled or 0):
        issues.append("Controlled Payment Entry cancellation evidence missing.")

    if int(review.payment_entry_docstatus_after_rollback or 0) != 2:
        issues.append("Payment Entry is not cancelled after rollback.")

    if flt(review.payment_entry_amount or 0, 2) != 2:
        issues.append("Expected smoke Payment Entry amount 2.00.")

    if int(review.invoice_count or 0) != 2:
        issues.append("Expected invoice count 2.")

    if flt(review.invoice_outstanding_after_rollback_total or 0, 2) != 2:
        issues.append("Expected restored outstanding 2.00.")

    if int(review.payment_entry_gl_count_after_rollback or 0) != 6:
        issues.append("Expected PE GL rows after rollback 6.")

    if flt(review.payment_entry_gl_net_after_rollback or 0, 2) != 0:
        issues.append("Expected PE GL net after rollback 0.00.")

    if int(review.recommended_max_batch_lines or 0) != 3:
        issues.append("Recommended max batch lines must be 3.")

    if flt(review.recommended_max_batch_amount or 0, 2) != 3:
        issues.append("Recommended max batch amount must be 3.00.")

    if int(review.recommended_payment_entry_count or 0) != 1:
        issues.append("Recommended Payment Entry count must be 1.")

    if review.payment_entry and frappe.db.exists("Payment Entry", review.payment_entry):
        docstatus = int(frappe.db.get_value("Payment Entry", review.payment_entry, "docstatus") or 0)
        if docstatus != 2:
            issues.append(f"Payment Entry current docstatus is not 2. Found {docstatus}.")

        gl_count, gl_net = pe_gl_count_net(review.payment_entry)
        if gl_count != int(review.payment_entry_gl_count_after_rollback or 0):
            issues.append("Current Payment Entry GL count does not match review evidence.")
        if flt(gl_net, 2) != 0:
            issues.append("Current Payment Entry GL net is not zero.")
    else:
        issues.append("Reviewed Payment Entry does not exist.")

    if guard["submitted_phase8e_smoke_pe_count"] != 0:
        issues.append(f"Submitted Phase 8E smoke PE count must be 0. Found {guard['submitted_phase8e_smoke_pe_count']}.")

    if guard["cancelled_phase8e_smoke_pe_count"] < 1:
        issues.append("Cancelled Phase 8E smoke PE count must be at least 1.")

    if guard["production_batch_enabled_policy_count"] != 0:
        issues.append("Controlled production batch enabled policy count is not zero.")

    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count is not zero.")

    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today is not zero.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today is not zero.")

    return issues


def build_items(review, config, guard, issues, ack_ok):
    items = []

    if review:
        add_item(
            items,
            "Pass",
            "Low",
            "Policy Review",
            "phase9a_review_exists",
            "Phase 9A policy review exists",
            f"Policy review found: {review.policy_review_id}.",
        )
    else:
        add_item(items, "Blocker", "Critical", "Policy Review", "phase9a_review_exists", "Phase 9A policy review exists", "No approved Phase 9A review found.")

    if not issues:
        add_item(items, "Pass", "Low", "Design Source", "design_source_valid", "Design source valid", "Phase 9A approval and Phase 8 smoke evidence are valid.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Design Source", "design_source_valid", "Design source valid", issue)

    add_item(items, "Pass", "Low", "Policy Design", "policy_mode", "Policy mode", "Limited Controlled Production Batch.")
    add_item(items, "Pass", "Low", "Policy Design", "max_batch_lines", "Max batch lines", "3 lines.")
    add_item(items, "Pass", "Low", "Policy Design", "max_batch_amount", "Max batch amount", "3.00.")
    add_item(items, "Pass", "Low", "Policy Design", "max_payment_entry_count", "Max Payment Entry count", "1 Payment Entry.")
    add_item(items, "Pass", "Low", "Policy Safety", "policy_live_disabled", "Policy live disabled", "Policy design is created with live posting disabled.")

    if config["production_mode"]:
        add_item(items, "Blocker", "Critical", "Site Config", "production_mode", "Production mode", "Production mode is enabled.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "production_mode", "Production mode", "Production mode remains disabled.")

    if config["live_pe_enabled"]:
        add_item(items, "Blocker", "Critical", "Site Config", "live_pe_enabled", "Live PE posting config", "Live PE posting config is enabled.")
    else:
        add_item(items, "Pass", "Low", "Site Config", "live_pe_enabled", "Live PE posting config", "Live PE posting config remains disabled.")

    if guard["production_batch_enabled_policy_count"] == 0 and guard["live_posting_allowed_policy_count"] == 0:
        add_item(items, "Pass", "Low", "Policy Safety", "live_policies_zero", "Live policies", "No controlled production live-enabled policies.")
    else:
        add_item(items, "Blocker", "Critical", "Policy Safety", "live_policies_zero", "Live policies", "Live-enabled controlled production policy found.")

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "policy_design_ack", "Policy design acknowledgement", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "policy_design_ack", "Policy design acknowledgement", f"Required acknowledgement not supplied: {POLICY_DESIGN_ACK}")

    return items


def design_rules():
    return [
        {
            "line_no": 1,
            "policy_rule": "Policy Mode",
            "rule_type": "Mode",
            "rule_value": "Limited Controlled Production Batch",
            "is_mandatory": 1,
            "status_detail": "Only limited controlled production batch preview flow is allowed.",
        },
        {
            "line_no": 2,
            "policy_rule": "Maximum Batch Lines",
            "rule_type": "Cap",
            "rule_value": "3",
            "is_mandatory": 1,
            "status_detail": "A batch cannot exceed 3 eligible lines.",
        },
        {
            "line_no": 3,
            "policy_rule": "Maximum Batch Amount",
            "rule_type": "Cap",
            "rule_value": "3.00",
            "is_mandatory": 1,
            "status_detail": "A batch cannot exceed 3.00 total allocation.",
        },
        {
            "line_no": 4,
            "policy_rule": "Maximum Payment Entry Count",
            "rule_type": "Cap",
            "rule_value": "1",
            "is_mandatory": 1,
            "status_detail": "Only one Payment Entry may be created during the limited preview/smoke path.",
        },
        {
            "line_no": 5,
            "policy_rule": "Require Preview",
            "rule_type": "Control",
            "rule_value": "1",
            "is_mandatory": 1,
            "status_detail": "Preview must be completed before any adapter or smoke step.",
        },
        {
            "line_no": 6,
            "policy_rule": "Require Adapter Hard Block",
            "rule_type": "Control",
            "rule_value": "1",
            "is_mandatory": 1,
            "status_detail": "Adapter must prove would-create evidence while hard-blocking live posting.",
        },
        {
            "line_no": 7,
            "policy_rule": "Require Activation Gate",
            "rule_type": "Control",
            "rule_value": "1",
            "is_mandatory": 1,
            "status_detail": "Activation gate must be approved before any controlled smoke.",
        },
        {
            "line_no": 8,
            "policy_rule": "Live Posting Disabled",
            "rule_type": "Safety",
            "rule_value": "0",
            "is_mandatory": 1,
            "status_detail": "Policy design does not enable production posting.",
        },
    ]


def create_design_items(doc):
    for rule in design_rules():
        item = frappe.new_doc("NDIS Limited Production Batch Policy Design Item")
        item.policy_design = doc.name
        item.line_no = rule["line_no"]
        item.policy_rule = rule["policy_rule"]
        item.rule_status = "Designed"
        item.rule_type = rule["rule_type"]
        item.rule_value = rule["rule_value"]
        item.is_live_enabled = 0
        item.is_mandatory = rule["is_mandatory"]
        item.status_detail = rule["status_detail"]
        item.source_doctype = "NDIS Controlled Production Batch Policy Review Gate"
        item.source_name = doc.policy_review_gate
        item.checked_on = doc.checked_on
        item.insert(ignore_permissions=True)


@frappe.whitelist()
def run_limited_production_batch_policy_design(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_limited_production_batch_policy_design")

    review = latest_policy_review_gate()
    config = config_state()
    guard_before = guardrails()
    ack_ok = acknowledgement == POLICY_DESIGN_ACK

    issues = validate_design_source(review, guard_before)
    items = build_items(review, config, guard_before, issues, ack_ok)

    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    complete = int(ack_ok and item_summary["blocker_count"] == 0 and review is not None)

    result = {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Designed" if complete else "Needs Review",
        "policy_design_status": "Ready For Limited Policy Preview" if complete else "Needs Review",
        "limited_policy_design_complete": complete,
        "ready_for_limited_policy_preview": complete,
        "production_batch_posting_allowed": 0,
        "real_posting_allowed": 0,
        "policy_live_enabled": 0,
        "policy_review_gate": review.name if review else None,
        "phase8g_freeze": review.phase8g_freeze if review else None,
        "rollback_run": review.rollback_run if review else None,
        "smoke_run": review.smoke_run if review else None,
        "activation_gate": review.activation_gate if review else None,
        "adapter_run": review.adapter_run if review else None,
        "preview": review.preview if review else None,
        "design_gate": review.design_gate if review else None,
        "phase7h_freeze": review.phase7h_freeze if review else None,
        "source_run": review.source_run if review else None,
        "company": review.company if review else None,
        "customer": review.customer if review else None,
        "payment_entry": review.payment_entry if review else None,
        "policy_mode": "Limited Controlled Production Batch",
        "max_batch_lines": 3,
        "max_batch_amount": 3,
        "max_payment_entry_count": 1,
        "allowed_payment_type": "Receive",
        "allowed_reference_doctype": "Sales Invoice",
        "requires_preview": 1,
        "requires_adapter_hard_block": 1,
        "requires_activation_gate": 1,
        "requires_posting_acknowledgement": 1,
        "requires_rollback_plan": 1,
        "payment_entry_docstatus_after_rollback": int(review.payment_entry_docstatus_after_rollback or 0) if review else 0,
        "payment_entry_amount": flt(review.payment_entry_amount or 0) if review else 0,
        "invoice_count": int(review.invoice_count or 0) if review else 0,
        "invoice_outstanding_after_rollback_total": flt(review.invoice_outstanding_after_rollback_total or 0) if review else 0,
        "payment_entry_gl_count_after_rollback": int(review.payment_entry_gl_count_after_rollback or 0) if review else 0,
        "payment_entry_gl_net_after_rollback": flt(review.payment_entry_gl_net_after_rollback or 0) if review else 0,
        "submitted_phase8e_smoke_pe_count": guard_before["submitted_phase8e_smoke_pe_count"],
        "cancelled_phase8e_smoke_pe_count": guard_before["cancelled_phase8e_smoke_pe_count"],
        "actual_payment_entry_created_count": 0,
        "actual_gl_created_count": 0,
        "policy_design_score": score,
        **item_summary,
        "items": items,
        "design_rules": design_rules(),
        "guardrails_before": guard_before,
        "guardrails_after": guardrails(),
        "config": config,
        "required_acknowledgement": POLICY_DESIGN_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 9B creates limited policy design records only. It enables no live policy and creates no accounting movement.",
    }

    if int(dry_run or 0):
        result["status"] = "Needs Review"
        result["policy_design_status"] = "Needs Review"
        result["limited_policy_design_complete"] = 0
        result["ready_for_limited_policy_preview"] = 0
        return result

    doc = frappe.new_doc("NDIS Limited Production Batch Policy Design")
    doc.policy_design_id = make_policy_design_id()
    doc.status = result["status"]
    doc.policy_design_status = result["policy_design_status"]
    doc.limited_policy_design_complete = complete
    doc.ready_for_limited_policy_preview = complete
    doc.production_batch_posting_allowed = 0
    doc.real_posting_allowed = 0
    doc.policy_live_enabled = 0

    for fieldname in [
        "policy_review_gate",
        "phase8g_freeze",
        "rollback_run",
        "smoke_run",
        "activation_gate",
        "adapter_run",
        "preview",
        "design_gate",
        "phase7h_freeze",
        "source_run",
        "company",
        "customer",
        "payment_entry",
        "policy_mode",
        "max_batch_lines",
        "max_batch_amount",
        "max_payment_entry_count",
        "allowed_payment_type",
        "allowed_reference_doctype",
        "requires_preview",
        "requires_adapter_hard_block",
        "requires_activation_gate",
        "requires_posting_acknowledgement",
        "requires_rollback_plan",
        "payment_entry_docstatus_after_rollback",
        "payment_entry_amount",
        "invoice_count",
        "invoice_outstanding_after_rollback_total",
        "payment_entry_gl_count_after_rollback",
        "payment_entry_gl_net_after_rollback",
        "submitted_phase8e_smoke_pe_count",
        "cancelled_phase8e_smoke_pe_count",
        "actual_payment_entry_created_count",
        "actual_gl_created_count",
        "policy_design_score",
        "blocker_count",
        "warning_count",
        "pass_count",
        "info_count",
        "item_count",
    ]:
        setattr(doc, fieldname, result.get(fieldname))

    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user

    doc.payment_entry_count_before = guard_before["payment_entry_count"]
    doc.payment_entry_count_after = guardrails()["payment_entry_count"]
    doc.payment_entry_gl_count_before = guard_before["payment_entry_gl_count"]
    doc.payment_entry_gl_count_after = guardrails()["payment_entry_gl_count"]
    doc.submitted_journal_entry_count_today = guard_before["submitted_journal_entry_count_today"]
    doc.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
    doc.production_batch_enabled_policy_count = guard_before["production_batch_enabled_policy_count"]
    doc.live_posting_allowed_policy_count = guard_before["live_posting_allowed_policy_count"]

    doc.required_acknowledgement = POLICY_DESIGN_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    if complete:
        create_design_items(doc)

    guard_after = guardrails()

    frappe.db.set_value(
        "NDIS Limited Production Batch Policy Design",
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
    result["policy_design"] = doc.name
    result["policy_design_id"] = doc.policy_design_id
    result["guardrails_after"] = guard_after

    return result


@frappe.whitelist()
def cancel_limited_production_batch_policy_design(policy_design, reason=None):
    assert_action("cancel_limited_production_batch_policy_design")

    if not frappe.db.exists("NDIS Limited Production Batch Policy Design", policy_design):
        frappe.throw(_("Policy design not found: {0}").format(policy_design))

    doc = frappe.get_doc("NDIS Limited Production Batch Policy Design", policy_design)

    if doc.status == "Cancelled":
        return {"policy_design": policy_design, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.limited_policy_design_complete or 0):
        frappe.throw(_("Cannot cancel a completed policy design. Create a superseding design instead."))

    frappe.db.set_value(
        "NDIS Limited Production Batch Policy Design",
        policy_design,
        {
            "status": "Cancelled",
            "policy_design_status": "Cancelled",
            "limited_policy_design_complete": 0,
            "ready_for_limited_policy_preview": 0,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 9B policy design audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        """
        UPDATE `tabNDIS Limited Production Batch Policy Design Item`
        SET rule_status = 'Cancelled'
        WHERE policy_design = %(policy_design)s
        """,
        {"policy_design": policy_design},
    )

    frappe.db.commit()

    return {
        "policy_design": policy_design,
        "status": "Cancelled",
        "note": "Policy design audit record cancelled only. No accounting movement occurred.",
    }


@frappe.whitelist()
def quick_limited_production_batch_policy_design_summary(limit=20):
    designs = frappe.get_all(
        "NDIS Limited Production Batch Policy Design",
        fields=[
            "name",
            "policy_design_id",
            "status",
            "policy_design_status",
            "limited_policy_design_complete",
            "ready_for_limited_policy_preview",
            "production_batch_posting_allowed",
            "real_posting_allowed",
            "policy_live_enabled",
            "policy_review_gate",
            "phase8g_freeze",
            "policy_mode",
            "max_batch_lines",
            "max_batch_amount",
            "max_payment_entry_count",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "policy_design_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    items = frappe.get_all(
        "NDIS Limited Production Batch Policy Design Item",
        fields=[
            "name",
            "policy_design",
            "line_no",
            "policy_rule",
            "rule_status",
            "rule_type",
            "rule_value",
            "is_live_enabled",
            "is_mandatory",
            "status_detail",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    return {
        "designs": designs,
        "items": items,
        "required_acknowledgement": POLICY_DESIGN_ACK,
        "guardrails": guardrails(),
        "config": config_state(),
        "note": "Phase 9B limited production batch policy design summary. No live posting enabled.",
    }


def execute_design_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("d.status = %(status)s")
        params["status"] = filters.get("status")

    columns = design_columns()

    data = frappe.db.sql(
        f"""
        SELECT
            d.name AS policy_design,
            d.policy_design_id,
            d.status,
            d.policy_design_status,
            d.limited_policy_design_complete,
            d.ready_for_limited_policy_preview,
            d.production_batch_posting_allowed,
            d.real_posting_allowed,
            d.policy_live_enabled,
            d.policy_review_gate,
            d.phase8g_freeze,
            d.policy_mode,
            d.max_batch_lines,
            d.max_batch_amount,
            d.max_payment_entry_count,
            d.actual_payment_entry_created_count,
            d.actual_gl_created_count,
            d.policy_design_score,
            d.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Limited Production Batch Policy Design` d
        {build_where(conditions)}
        ORDER BY d.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.policy_design_id for row in data[:20]],
            "datasets": [
                {"name": "Designed", "values": [int(row.limited_policy_design_complete or 0) for row in data[:20]]},
                {"name": "Live Enabled", "values": [int(row.policy_live_enabled or 0) for row in data[:20]]},
                {"name": "Actual PE", "values": [int(row.actual_payment_entry_created_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Policy Designs"), "datatype": "Int"},
        {"value": sum(int(row.limited_policy_design_complete or 0) for row in data), "indicator": "Green", "label": _("Designed"), "datatype": "Int"},
        {"value": sum(flt(row.max_batch_amount or 0) for row in data), "indicator": "Blue", "label": _("Batch Cap"), "datatype": "Currency", "currency": currency()},
        {"value": sum(int(row.policy_live_enabled or 0) for row in data), "indicator": "Red", "label": _("Live Enabled"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def design_columns():
    return [
        {"fieldname": "policy_design", "label": _("Policy Design"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Policy Design", "width": 220},
        {"fieldname": "policy_design_id", "label": _("Policy Design ID"), "fieldtype": "Data", "width": 430},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "policy_design_status", "label": _("Design Status"), "fieldtype": "Data", "width": 260},
        {"fieldname": "ready_for_limited_policy_preview", "label": _("Ready Preview"), "fieldtype": "Check", "width": 120},
        {"fieldname": "policy_mode", "label": _("Policy Mode"), "fieldtype": "Data", "width": 250},
        {"fieldname": "max_batch_lines", "label": _("Max Lines"), "fieldtype": "Int", "width": 90},
        {"fieldname": "max_batch_amount", "label": _("Max Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
        {"fieldname": "max_payment_entry_count", "label": _("Max PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "policy_live_enabled", "label": _("Live Enabled"), "fieldtype": "Check", "width": 110},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "policy_design_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("policy_design"):
        conditions.append("i.policy_design = %(policy_design)s")
        params["policy_design"] = filters.get("policy_design")

    if filters.get("rule_status"):
        conditions.append("i.rule_status = %(rule_status)s")
        params["rule_status"] = filters.get("rule_status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Policy Design Item", "width": 220},
        {"fieldname": "policy_design", "label": _("Policy Design"), "fieldtype": "Link", "options": "NDIS Limited Production Batch Policy Design", "width": 220},
        {"fieldname": "line_no", "label": _("Line No"), "fieldtype": "Int", "width": 80},
        {"fieldname": "policy_rule", "label": _("Policy Rule"), "fieldtype": "Data", "width": 260},
        {"fieldname": "rule_status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "rule_type", "label": _("Type"), "fieldtype": "Data", "width": 110},
        {"fieldname": "rule_value", "label": _("Value"), "fieldtype": "Data", "width": 120},
        {"fieldname": "is_live_enabled", "label": _("Live Enabled"), "fieldtype": "Check", "width": 110},
        {"fieldname": "is_mandatory", "label": _("Mandatory"), "fieldtype": "Check", "width": 100},
        {"fieldname": "status_detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 480},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item,
            i.policy_design,
            i.line_no,
            i.policy_rule,
            i.rule_status,
            i.rule_type,
            i.rule_value,
            i.is_live_enabled,
            i.is_mandatory,
            i.status_detail,
            i.checked_on
        FROM `tabNDIS Limited Production Batch Policy Design Item` i
        {build_where(conditions)}
        ORDER BY i.policy_design DESC, i.line_no ASC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.policy_rule for row in data[:20]],
            "datasets": [{"name": "Live Enabled", "values": [int(row.is_live_enabled or 0) for row in data[:20]]}],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Rules"), "datatype": "Int"},
        {"value": len([row for row in data if row.rule_status == "Designed"]), "indicator": "Green", "label": _("Designed"), "datatype": "Int"},
        {"value": sum(int(row.is_live_enabled or 0) for row in data), "indicator": "Red", "label": _("Live Enabled"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_design_report(filters)

    guard = guardrails()

    summary.append({"value": guard["payment_entry_count"], "indicator": "Blue", "label": _("Payment Entry Count"), "datatype": "Int"})
    summary.append({"value": guard["payment_entry_gl_count"], "indicator": "Blue", "label": _("Payment Entry GL Count"), "datatype": "Int"})
    summary.append({"value": guard["submitted_journal_entry_count_today"], "indicator": "Red", "label": _("Submitted JE Today"), "datatype": "Int"})
    summary.append({"value": guard["purchase_invoice_count_today"], "indicator": "Red", "label": _("Purchase Invoice Today"), "datatype": "Int"})
    summary.append({"value": guard["production_batch_enabled_policy_count"], "indicator": "Red", "label": _("Production Batch Enabled Policies"), "datatype": "Int"})
    summary.append({"value": guard["live_posting_allowed_policy_count"], "indicator": "Red", "label": _("Live Posting Allowed Policies"), "datatype": "Int"})

    return columns, data, message, chart, summary


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)
