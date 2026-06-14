import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.permissions import assert_action


SMOKE_ACK = "I_CONFIRM_PHASE10J_EXECUTE_SINGLE_GUARDED_LIMITED_OPERATION_SMOKE_CREATE_ONE_PE"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"


def make_smoke_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-SINGLE-GUARDED-LIMITED-OP-SMOKE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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
    if not name or not has_column(doctype, fieldname):
        return default
    return int(frappe.db.get_value(doctype, name, fieldname) or 0)


def production_batch_enabled_policy_count():
    if not frappe.db.exists("DocType", POLICY_DOCTYPE):
        return 0
    if not has_column(POLICY_DOCTYPE, "production_batch_enabled"):
        return 0
    return count_dt(POLICY_DOCTYPE, {"production_batch_enabled": 1})


def live_posting_allowed_policy_count():
    if not frappe.db.exists("DocType", POLICY_DOCTYPE):
        return 0
    if not has_column(POLICY_DOCTYPE, "live_posting_allowed"):
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


def latest_gate():
    rows = frappe.get_all(
        "NDIS Guarded Limited Operation Execution Gate",
        filters={
            "status": "Execution Allowed",
            "execution_status": "Ready For One Guarded Limited Operation Smoke Execution",
            "execution_gate_allowed": 1,
            "ready_for_single_guarded_operation_smoke": 1,
            "smoke_only_allowed": 1,
            "real_posting_allowed": 0,
            "execution_not_performed": 1,
            "operation_shape_locked": 1,
            "one_operation_only": 1,
            "policy_state_preserved_verified": 1,
            "policy_mutation_performed": 0,
            "actual_policy_mutation_count": 0,
            "phase10h_preview_verified": 1,
            "phase10g_pre_check_verified": 1,
            "phase10f_register_verified": 1,
            "phase10e_decision_verified": 1,
            "payment_entry_cancelled_verified": 1,
            "no_new_accounting_movement_verified": 1,
            "controlled_policy_enabled_verified": 1,
            "live_posting_blocked_verified": 1,
            "target_policy_enabled_after": 1,
            "target_policy_live_after": 0,
            "locked_batch_line_count": 3,
            "locked_payment_entry_count": 1,
            "locked_live_posting_requested": 0,
            "locked_journal_entry_side_effect_requested": 0,
            "locked_purchase_invoice_side_effect_requested": 0,
            "would_create_payment_entry_count": 1,
            "would_create_gl_entry_count": 0,
            "would_post_live": 0,
            "would_create_journal_entry": 0,
            "would_create_purchase_invoice": 0,
            "actual_execution_performed": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
            "submitted_journal_entry_count_today": 0,
            "purchase_invoice_count_today": 0,
        },
        fields=[
            "name",
            "gate_id",
            "preview",
            "pre_check",
            "monitoring_register",
            "decision",
            "review",
            "runtime_guard",
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
            "target_policy_enabled_before",
            "target_policy_enabled_after",
            "target_policy_live_before",
            "target_policy_live_after",
            "production_batch_enabled_policy_count_before",
            "production_batch_enabled_policy_count_after",
            "live_posting_allowed_policy_count_before",
            "live_posting_allowed_policy_count_after",
            "locked_batch_line_count",
            "locked_batch_amount",
            "locked_payment_entry_count",
            "locked_live_posting_requested",
            "locked_journal_entry_side_effect_requested",
            "locked_purchase_invoice_side_effect_requested",
            "payment_entry",
            "payment_entry_docstatus",
            "payment_entry_status",
            "gate_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )

    return rows[0] if rows else None


def existing_smoke_for_gate(gate):
    rows = frappe.get_all(
        "NDIS Single Guarded Limited Operation Smoke",
        filters={
            "execution_gate": gate,
            "status": "Smoke Completed - Rollback Required",
            "smoke_execution_completed": 1,
            "rollback_required": 1,
        },
        fields=["name", "smoke_id", "payment_entry"],
        limit=1,
    )
    return rows[0] if rows else None


def validate_gate(gate, guard, policy_enabled_before, policy_live_before):
    issues = []

    if not gate:
        issues.append("No Phase 10I execution-allowed gate found.")
        return issues

    existing = existing_smoke_for_gate(gate.name)
    if existing:
        issues.append(f"Phase 10J smoke already exists for this execution gate: {existing.smoke_id} / {existing.payment_entry}")

    required_links = {
        "execution_gate": ("NDIS Guarded Limited Operation Execution Gate", gate.name),
        "preview": ("NDIS Guarded Limited Operation Preview", gate.preview),
        "pre_check": ("NDIS Controlled Limited Operation Pre Check", gate.pre_check),
        "monitoring_register": ("NDIS Controlled Limited Operations Monitoring Register", gate.monitoring_register),
        "target_policy": (POLICY_DOCTYPE, gate.target_policy),
    }

    for label, pair in required_links.items():
        doctype, name = pair
        if not name:
            issues.append(f"Missing evidence link: {label}")
        elif not frappe.db.exists(doctype, name):
            issues.append(f"Linked evidence does not exist: {doctype} {name}")

    if int(gate.locked_batch_line_count or 0) != 3:
        issues.append("Locked batch line count must be exactly 3.")

    if flt(gate.locked_batch_amount or 0, 2) != 3:
        issues.append("Locked batch amount must be exactly 3.00.")

    if int(gate.locked_payment_entry_count or 0) != 1:
        issues.append("Locked Payment Entry count must be exactly 1.")

    if int(gate.locked_live_posting_requested or 0) != 0:
        issues.append("Locked live posting request must be 0.")

    if int(gate.locked_journal_entry_side_effect_requested or 0) != 0:
        issues.append("Locked Journal Entry side effect request must be 0.")

    if int(gate.locked_purchase_invoice_side_effect_requested or 0) != 0:
        issues.append("Locked Purchase Invoice side effect request must be 0.")

    if policy_enabled_before != 1:
        issues.append("Target policy production_batch_enabled must be 1.")

    if policy_live_before != 0:
        issues.append("Target policy live_posting_allowed must be 0.")

    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must remain enabled.")

    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must remain 0.")

    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry count today must be 0 before Phase 10J smoke.")

    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice count today must be 0 before Phase 10J smoke.")

    return issues


def get_template_payment_entry(gate):
    if gate.payment_entry and frappe.db.exists("Payment Entry", gate.payment_entry):
        return frappe.get_doc("Payment Entry", gate.payment_entry)

    rows = frappe.get_all(
        "Payment Entry",
        filters={"docstatus": 2},
        fields=["name"],
        order_by="creation desc",
        limit=1,
    )

    if rows:
        return frappe.get_doc("Payment Entry", rows[0].name)

    frappe.throw(_("No cancelled historical smoke Payment Entry found to use as template."))


def find_reference_invoices(template, required_count=3, per_reference_amount=1):
    company = template.company
    party_type = template.party_type
    template_party = template.party

    if party_type != "Customer":
        frappe.throw(_("Phase 10J currently supports Customer receipt smoke only. Template party_type is {0}.").format(party_type))

    rows = frappe.get_all(
        "Sales Invoice",
        filters={
            "docstatus": 1,
            "company": company,
            "outstanding_amount": [">=", per_reference_amount],
        },
        fields=["name", "customer", "outstanding_amount", "grand_total", "currency", "posting_date"],
        order_by="customer asc, posting_date asc, creation asc",
        limit=100,
    )

    grouped = {}
    for row in rows:
        grouped.setdefault(row.customer, []).append(row)

    candidate_party = None
    if len(grouped.get(template_party, [])) >= required_count:
        candidate_party = template_party
    else:
        candidates = [party for party, invoices in grouped.items() if len(invoices) >= required_count]
        candidate_party = sorted(candidates)[0] if candidates else None

    if not candidate_party:
        best_count = max([len(invoices) for invoices in grouped.values()] or [0])
        frappe.throw(
            _(
                "Phase 10J requires exactly {0} open Sales Invoices for one customer in company {1}, each with at least {2} outstanding. Best available customer count is {3}."
            ).format(required_count, company, per_reference_amount, best_count)
        )

    selected = []

    for row in grouped[candidate_party]:
        if len(selected) >= required_count:
            break

        # Do not use the same invoice twice.
        if row.name in [x["reference_name"] for x in selected]:
            continue

        selected.append(
            {
                "reference_doctype": "Sales Invoice",
                "reference_name": row.name,
                "customer": row.customer,
                "allocated_amount": flt(per_reference_amount, 2),
                "outstanding_amount": flt(row.outstanding_amount, 2),
                "total_amount": flt(row.grand_total, 2),
            }
        )

    if len(selected) != required_count:
        frappe.throw(
            _(
                "Phase 10J requires exactly {0} open Sales Invoices for customer {1}, each with at least {2} outstanding. Found {3}."
            ).format(required_count, candidate_party, per_reference_amount, len(selected))
        )

    return selected


def copy_if_has(target, source, fieldname):
    if target.meta.has_field(fieldname) and source.meta.has_field(fieldname):
        value = source.get(fieldname)
        if value not in (None, ""):
            target.set(fieldname, value)


def build_payment_entry_from_template(template, references, gate):
    total_amount = sum(flt(row["allocated_amount"], 2) for row in references)

    pe = frappe.new_doc("Payment Entry")

    header_fields = [
        "naming_series",
        "payment_type",
        "company",
        "posting_date",
        "mode_of_payment",
        "party_type",
        "party",
        "party_name",
        "bank_account",
        "paid_from",
        "paid_from_account_type",
        "paid_from_account_currency",
        "paid_to",
        "paid_to_account_type",
        "paid_to_account_currency",
        "source_exchange_rate",
        "target_exchange_rate",
        "paid_from_account_balance",
        "paid_to_account_balance",
        "cost_center",
        "project",
    ]

    for fieldname in header_fields:
        copy_if_has(pe, template, fieldname)

    reference_customer = references[0].get("customer")
    pe.party = reference_customer
    pe.party_name = frappe.db.get_value("Customer", reference_customer, "customer_name") or reference_customer
    pe.posting_date = today()
    pe.paid_amount = total_amount
    pe.received_amount = total_amount
    pe.base_paid_amount = total_amount
    pe.base_received_amount = total_amount
    pe.reference_no = gate.gate_id
    pe.reference_date = today()
    pe.remarks = (
        "Phase 10J single guarded limited operation smoke execution. "
        "Rollback required immediately after verification."
    )

    for ref in references:
        pe.append(
            "references",
            {
                "reference_doctype": ref["reference_doctype"],
                "reference_name": ref["reference_name"],
                "allocated_amount": ref["allocated_amount"],
            },
        )

    pe.insert(ignore_permissions=True)
    pe.submit()

    return pe


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


def build_items(gate, issues, ack_ok, created_pe=None, references=None, guard_before=None, guard_after=None):
    items = []

    if gate:
        add_item(
            items,
            "Pass",
            "Low",
            "Evidence",
            "phase10i_gate_exists",
            "Phase 10I execution gate exists",
            f"Gate found: {gate.gate_id}.",
            "NDIS Guarded Limited Operation Execution Gate",
            gate.name,
        )
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase10i_gate_exists", "Phase 10I execution gate exists", "No execution gate found.")

    if not issues:
        add_item(items, "Pass", "Low", "Gate Source", "gate_source_valid", "Gate source valid", "Execution gate valid for Phase 10J smoke.")
    else:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Gate Source", "gate_source_valid", "Gate source valid", issue)

    if created_pe:
        add_item(items, "Pass", "High", "Accounting", "payment_entry_created", "Exactly one Payment Entry created", created_pe.name, "Payment Entry", created_pe.name)
        add_item(items, "Pass", "High", "Accounting", "payment_entry_submitted", "Payment Entry submitted", f"docstatus={created_pe.docstatus}, status={created_pe.status}", "Payment Entry", created_pe.name)
        add_item(items, "Pass", "High", "Accounting", "payment_entry_amount", "Payment Entry amount is 3.00", f"paid_amount={flt(created_pe.paid_amount, 2)}")
        add_item(items, "Pass", "High", "Accounting", "payment_entry_refs", "Payment Entry has 3 references", f"references={len(created_pe.references or [])}")

    if references:
        for ref in references:
            add_item(
                items,
                "Pass",
                "Low",
                "Reference",
                "reference_allocated",
                f"Reference {ref['reference_name']} allocated",
                f"allocated_amount={ref['allocated_amount']}, outstanding_before={ref['outstanding_amount']}",
                ref["reference_doctype"],
                ref["reference_name"],
            )

    if guard_before and guard_after:
        add_item(
            items,
            "Pass",
            "High",
            "Guardrail",
            "actual_movement_shape",
            "Actual movement shape recorded",
            f"PE {guard_before['payment_entry_count']} -> {guard_after['payment_entry_count']}; PE GL {guard_before['payment_entry_gl_count']} -> {guard_after['payment_entry_gl_count']}",
        )

    add_item(
        items,
        "Warning",
        "High",
        "Rollback",
        "rollback_required",
        "Rollback required immediately",
        "Phase 10J intentionally leaves the submitted Payment Entry live for Phase 10K rollback.",
    )

    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {SMOKE_ACK}")

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
        row = frappe.new_doc("NDIS Single Guarded Limited Operation Smoke Item")
        row.smoke = doc.name
        row.status = item["status"]
        row.severity = item["severity"]
        row.category = item["category"]
        row.check_key = item["check_key"]
        row.check_label = item["check_label"]
        row.detail = item["detail"]
        row.source_doctype = item.get("source_doctype")
        row.source_name = item.get("source_name")
        row.checked_on = doc.checked_on
        row.insert(ignore_permissions=True)


@frappe.whitelist()
def run_single_guarded_limited_operation_smoke(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_single_guarded_limited_operation_smoke")

    gate = latest_gate()

    config = {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }

    guard_before = guardrails()
    ack_ok = acknowledgement == SMOKE_ACK

    policy_enabled_before = get_flag(POLICY_DOCTYPE, gate.target_policy, "production_batch_enabled") if gate else 0
    policy_live_before = get_flag(POLICY_DOCTYPE, gate.target_policy, "live_posting_allowed") if gate else 0

    issues = validate_gate(gate, guard_before, policy_enabled_before, policy_live_before)

    template = None
    references = []

    if gate and not issues:
        template = get_template_payment_entry(gate)
        references = find_reference_invoices(template, required_count=3, per_reference_amount=1)

    if not ack_ok:
        issues_for_record = list(issues)
    else:
        issues_for_record = issues

    allowed = int(ack_ok and len(issues_for_record) == 0 and bool(gate))

    if int(dry_run or 0):
        items = build_items(gate, issues_for_record, ack_ok, None, references, guard_before, guard_before)
        item_summary = summarise_items(items)
        score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

        return {
            "dry_run": True,
            "status": "Needs Review",
            "smoke_status": "Needs Review",
            "would_execute": int(len(issues_for_record) == 0 and gate is not None),
            "references": references,
            "required_acknowledgement": SMOKE_ACK,
            "acknowledgement_ok": ack_ok,
            "guardrails_before": guard_before,
            "guardrails_after": guardrails(),
            "smoke_score": score,
            **item_summary,
            "items": items,
            "issues": issues_for_record,
            "note": "Dry-run only. No Payment Entry or GL created.",
        }

    if not allowed:
        items = build_items(gate, issues_for_record, ack_ok, None, references, guard_before, guard_before)
        item_summary = summarise_items(items)
        score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

        doc = frappe.new_doc("NDIS Single Guarded Limited Operation Smoke")
        doc.smoke_id = make_smoke_id()
        doc.status = "Needs Review"
        doc.smoke_status = "Needs Review"
        doc.execution_gate = gate.name if gate else None
        doc.preview = gate.preview if gate else None
        doc.pre_check = gate.pre_check if gate else None
        doc.monitoring_register = gate.monitoring_register if gate else None
        doc.decision = gate.decision if gate else None
        doc.runtime_guard = gate.runtime_guard if gate else None
        doc.target_policy_doctype = POLICY_DOCTYPE
        doc.target_policy = gate.target_policy if gate else None
        doc.target_policy_name = gate.target_policy_name if gate else None
        doc.target_policy_enabled_before = policy_enabled_before
        doc.target_policy_enabled_after = policy_enabled_before
        doc.target_policy_live_before = policy_live_before
        doc.target_policy_live_after = policy_live_before
        doc.payment_entry_count_before = guard_before["payment_entry_count"]
        doc.payment_entry_count_after = guard_before["payment_entry_count"]
        doc.payment_entry_gl_count_before = guard_before["payment_entry_gl_count"]
        doc.payment_entry_gl_count_after = guard_before["payment_entry_gl_count"]
        doc.actual_payment_entry_created_count = 0
        doc.actual_gl_created_count = 0
        doc.submitted_journal_entry_count_today = guard_before["submitted_journal_entry_count_today"]
        doc.purchase_invoice_count_today = guard_before["purchase_invoice_count_today"]
        doc.smoke_score = score
        doc.blocker_count = item_summary["blocker_count"]
        doc.warning_count = item_summary["warning_count"]
        doc.pass_count = item_summary["pass_count"]
        doc.info_count = item_summary["info_count"]
        doc.item_count = item_summary["item_count"]
        doc.site_name = frappe.local.site
        doc.sandbox_config_enabled = config["sandbox_enabled"]
        doc.production_mode_detected = config["production_mode"]
        doc.live_payment_entry_posting_config = config["live_pe_enabled"]
        doc.checked_on = now_datetime()
        doc.checked_by = frappe.session.user
        doc.required_acknowledgement = SMOKE_ACK
        doc.acknowledgement = acknowledgement
        doc.acknowledgement_ok = int(ack_ok)
        doc.summary_json = safe_json({"issues": issues_for_record, "guardrails": guard_before})
        doc.reference_json = safe_json(references)
        doc.notes = notes
        doc.insert(ignore_permissions=True)

        create_items(doc, items)
        frappe.db.commit()

        return {
            "created": True,
            "smoke": doc.name,
            "smoke_id": doc.smoke_id,
            "status": doc.status,
            "smoke_status": doc.smoke_status,
            "issues": issues_for_record,
            "guardrails_after": guardrails(),
        }

    created_pe = build_payment_entry_from_template(template, references, gate)
    guard_after = guardrails()

    policy_enabled_after = get_flag(POLICY_DOCTYPE, gate.target_policy, "production_batch_enabled")
    policy_live_after = get_flag(POLICY_DOCTYPE, gate.target_policy, "live_posting_allowed")

    pe_gl_rows = count_dt("GL Entry", {"voucher_type": "Payment Entry", "voucher_no": created_pe.name})

    actual_pe_created = guard_after["payment_entry_count"] - guard_before["payment_entry_count"]
    actual_gl_created = guard_after["payment_entry_gl_count"] - guard_before["payment_entry_gl_count"]

    blockers = []

    if actual_pe_created != 1:
        blockers.append(f"Expected exactly 1 Payment Entry created; got {actual_pe_created}")

    if flt(created_pe.paid_amount, 2) != 3:
        blockers.append(f"Expected Payment Entry amount 3.00; got {flt(created_pe.paid_amount, 2)}")

    if len(created_pe.references or []) != 3:
        blockers.append(f"Expected 3 Payment Entry references; got {len(created_pe.references or [])}")

    if int(created_pe.docstatus or 0) != 1:
        blockers.append(f"Expected submitted Payment Entry docstatus 1; got {created_pe.docstatus}")

    if guard_after["submitted_journal_entry_count_today"] != guard_before["submitted_journal_entry_count_today"]:
        blockers.append("Journal Entry count changed during Phase 10J smoke.")

    if guard_after["purchase_invoice_count_today"] != guard_before["purchase_invoice_count_today"]:
        blockers.append("Purchase Invoice count changed during Phase 10J smoke.")

    if policy_enabled_before != 1 or policy_enabled_after != 1 or policy_live_before != 0 or policy_live_after != 0:
        blockers.append("Policy state changed or is not enabled/live-blocked.")

    items = build_items(gate, blockers, ack_ok, created_pe, references, guard_before, guard_after)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])

    completed = int(item_summary["blocker_count"] == 0)

    doc = frappe.new_doc("NDIS Single Guarded Limited Operation Smoke")
    doc.smoke_id = make_smoke_id()
    doc.status = "Smoke Completed - Rollback Required" if completed else "Blocked"
    doc.smoke_status = "Single Guarded Limited Operation Smoke Completed" if completed else "Blocked"

    doc.smoke_execution_completed = completed
    doc.rollback_required = completed
    doc.freeze_required_after_rollback = completed
    doc.ready_for_single_operation_smoke_rollback = completed
    doc.execution_gate_consumed = completed
    doc.single_operation_only = 1
    doc.policy_state_preserved_verified = int(policy_enabled_before == 1 and policy_enabled_after == 1 and policy_live_before == 0 and policy_live_after == 0)
    doc.policy_mutation_performed = 0
    doc.actual_policy_mutation_count = 0

    doc.phase10i_gate_verified = 1
    doc.phase10h_preview_verified = 1
    doc.phase10g_pre_check_verified = 1
    doc.phase10f_register_verified = 1
    doc.controlled_policy_enabled_verified = int(policy_enabled_after == 1)
    doc.live_posting_blocked_verified = int(policy_live_after == 0)

    doc.execution_gate = gate.name
    doc.preview = gate.preview
    doc.pre_check = gate.pre_check
    doc.monitoring_register = gate.monitoring_register
    doc.decision = gate.decision
    doc.review = gate.review
    doc.runtime_guard = gate.runtime_guard

    doc.target_policy_doctype = POLICY_DOCTYPE
    doc.target_policy = gate.target_policy
    doc.target_policy_name = gate.target_policy_name
    doc.target_policy_enabled_before = policy_enabled_before
    doc.target_policy_enabled_after = policy_enabled_after
    doc.target_policy_live_before = policy_live_before
    doc.target_policy_live_after = policy_live_after
    doc.production_batch_enabled_policy_count_before = guard_before["production_batch_enabled_policy_count"]
    doc.production_batch_enabled_policy_count_after = guard_after["production_batch_enabled_policy_count"]
    doc.live_posting_allowed_policy_count_before = guard_before["live_posting_allowed_policy_count"]
    doc.live_posting_allowed_policy_count_after = guard_after["live_posting_allowed_policy_count"]

    doc.locked_batch_line_count = int(gate.locked_batch_line_count or 0)
    doc.locked_batch_amount = flt(gate.locked_batch_amount or 0, 2)
    doc.locked_payment_entry_count = int(gate.locked_payment_entry_count or 0)

    doc.payment_entry = created_pe.name
    doc.payment_entry_docstatus = int(created_pe.docstatus or 0)
    doc.payment_entry_status = created_pe.status
    doc.payment_entry_amount = flt(created_pe.paid_amount, 2)
    doc.payment_entry_reference_count = len(created_pe.references or [])
    doc.payment_entry_gl_row_count = pe_gl_rows
    doc.payment_entry_naming_series = created_pe.naming_series
    doc.payment_type = created_pe.payment_type
    doc.party_type = created_pe.party_type
    doc.party = created_pe.party
    doc.company = created_pe.company

    doc.payment_entry_count_before = guard_before["payment_entry_count"]
    doc.payment_entry_count_after = guard_after["payment_entry_count"]
    doc.payment_entry_gl_count_before = guard_before["payment_entry_gl_count"]
    doc.payment_entry_gl_count_after = guard_after["payment_entry_gl_count"]
    doc.actual_payment_entry_created_count = actual_pe_created
    doc.actual_gl_created_count = actual_gl_created
    doc.submitted_journal_entry_count_today = guard_after["submitted_journal_entry_count_today"]
    doc.purchase_invoice_count_today = guard_after["purchase_invoice_count_today"]

    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.smoke_score = score
    doc.blocker_count = item_summary["blocker_count"]
    doc.warning_count = item_summary["warning_count"]
    doc.pass_count = item_summary["pass_count"]
    doc.info_count = item_summary["info_count"]
    doc.item_count = item_summary["item_count"]
    doc.required_acknowledgement = SMOKE_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(
        {
            "payment_entry": created_pe.name,
            "references": references,
            "guardrails_before": guard_before,
            "guardrails_after": guard_after,
            "blockers": blockers,
            "rollback_required": completed,
        }
    )
    doc.reference_json = safe_json(references)
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    create_items(doc, items)
    frappe.db.commit()

    return {
        "created": True,
        "smoke": doc.name,
        "smoke_id": doc.smoke_id,
        "status": doc.status,
        "smoke_status": doc.smoke_status,
        "payment_entry": created_pe.name,
        "payment_entry_docstatus": created_pe.docstatus,
        "payment_entry_status": created_pe.status,
        "payment_entry_amount": flt(created_pe.paid_amount, 2),
        "payment_entry_reference_count": len(created_pe.references or []),
        "payment_entry_gl_row_count": pe_gl_rows,
        "actual_payment_entry_created_count": actual_pe_created,
        "actual_gl_created_count": actual_gl_created,
        "rollback_required": doc.rollback_required,
        "freeze_required_after_rollback": doc.freeze_required_after_rollback,
        "ready_for_single_operation_smoke_rollback": doc.ready_for_single_operation_smoke_rollback,
        "guardrails_before": guard_before,
        "guardrails_after": guard_after,
        "references": references,
        "blockers": blockers,
    }


@frappe.whitelist()
def cancel_single_guarded_limited_operation_smoke_audit(smoke, reason=None):
    assert_action("cancel_single_guarded_limited_operation_smoke_audit")

    if not frappe.db.exists("NDIS Single Guarded Limited Operation Smoke", smoke):
        frappe.throw(_("Smoke audit not found: {0}").format(smoke))

    doc = frappe.get_doc("NDIS Single Guarded Limited Operation Smoke", smoke)

    if doc.status == "Cancelled":
        return {"smoke": smoke, "status": "Cancelled", "note": "Already cancelled."}

    if int(doc.smoke_execution_completed or 0) or doc.payment_entry:
        frappe.throw(_("Cannot cancel a completed Phase 10J smoke audit. Roll back the Payment Entry in Phase 10K."))

    frappe.db.set_value(
        "NDIS Single Guarded Limited Operation Smoke",
        smoke,
        {
            "status": "Cancelled",
            "smoke_status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 10J no-ack smoke audit cancelled.",
        },
        update_modified=False,
    )

    frappe.db.sql(
        """
        UPDATE `tabNDIS Single Guarded Limited Operation Smoke Item`
        SET status = 'Cancelled'
        WHERE smoke = %(smoke)s
        """,
        {"smoke": smoke},
    )

    frappe.db.commit()

    return {
        "smoke": smoke,
        "status": "Cancelled",
        "note": "No-ack smoke audit cancelled only. No accounting or policy movement occurred.",
    }


@frappe.whitelist()
def quick_single_guarded_limited_operation_smoke_summary(limit=20):
    smokes = frappe.get_all(
        "NDIS Single Guarded Limited Operation Smoke",
        fields=[
            "name",
            "smoke_id",
            "status",
            "smoke_status",
            "smoke_execution_completed",
            "rollback_required",
            "freeze_required_after_rollback",
            "ready_for_single_operation_smoke_rollback",
            "execution_gate",
            "payment_entry",
            "payment_entry_docstatus",
            "payment_entry_status",
            "payment_entry_amount",
            "payment_entry_reference_count",
            "payment_entry_gl_row_count",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "production_batch_enabled_policy_count_after",
            "live_posting_allowed_policy_count_after",
            "submitted_journal_entry_count_today",
            "purchase_invoice_count_today",
            "smoke_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    items = frappe.get_all(
        "NDIS Single Guarded Limited Operation Smoke Item",
        fields=[
            "name",
            "smoke",
            "status",
            "severity",
            "category",
            "check_label",
            "detail",
            "source_doctype",
            "source_name",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )

    return {
        "smokes": smokes,
        "items": items,
        "required_acknowledgement": SMOKE_ACK,
        "guardrails": guardrails(),
        "note": "Phase 10J single guarded limited operation smoke summary. Completed smoke requires Phase 10K rollback.",
    }


def execute_smoke_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}

    if filters.get("status"):
        conditions.append("s.status = %(status)s")
        params["status"] = filters.get("status")

    columns = smoke_columns()

    data = frappe.db.sql(
        f"""
        SELECT
            s.name AS smoke,
            s.smoke_id,
            s.status,
            s.smoke_status,
            s.smoke_execution_completed,
            s.rollback_required,
            s.freeze_required_after_rollback,
            s.ready_for_single_operation_smoke_rollback,
            s.execution_gate,
            s.payment_entry,
            s.payment_entry_docstatus,
            s.payment_entry_status,
            s.payment_entry_amount,
            s.payment_entry_reference_count,
            s.payment_entry_gl_row_count,
            s.actual_payment_entry_created_count,
            s.actual_gl_created_count,
            s.production_batch_enabled_policy_count_after,
            s.live_posting_allowed_policy_count_after,
            s.submitted_journal_entry_count_today,
            s.purchase_invoice_count_today,
            s.smoke_score,
            s.checked_on,
            %(currency)s AS currency
        FROM `tabNDIS Single Guarded Limited Operation Smoke` s
        {build_where(conditions)}
        ORDER BY s.creation DESC
        """,
        params,
        as_dict=True,
    )

    chart = {
        "data": {
            "labels": [row.smoke_id for row in data[:20]],
            "datasets": [
                {"name": "PE Created", "values": [int(row.actual_payment_entry_created_count or 0) for row in data[:20]]},
                {"name": "GL Created", "values": [int(row.actual_gl_created_count or 0) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Smokes"), "datatype": "Int"},
        {"value": sum(int(row.smoke_execution_completed or 0) for row in data), "indicator": "Green", "label": _("Completed"), "datatype": "Int"},
        {"value": sum(int(row.rollback_required or 0) for row in data), "indicator": "Orange", "label": _("Rollback Required"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def smoke_columns():
    return [
        {"fieldname": "smoke", "label": _("Smoke"), "fieldtype": "Link", "options": "NDIS Single Guarded Limited Operation Smoke", "width": 220},
        {"fieldname": "smoke_id", "label": _("Smoke ID"), "fieldtype": "Data", "width": 420},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 210},
        {"fieldname": "smoke_status", "label": _("Smoke Status"), "fieldtype": "Data", "width": 330},
        {"fieldname": "smoke_execution_completed", "label": _("Completed"), "fieldtype": "Check", "width": 95},
        {"fieldname": "rollback_required", "label": _("Rollback Required"), "fieldtype": "Check", "width": 130},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "payment_entry_docstatus", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 105},
        {"fieldname": "payment_entry_status", "label": _("PE Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "payment_entry_amount", "label": _("PE Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "payment_entry_reference_count", "label": _("Refs"), "fieldtype": "Int", "width": 70},
        {"fieldname": "payment_entry_gl_row_count", "label": _("Voucher GL Rows"), "fieldtype": "Int", "width": 130},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "production_batch_enabled_policy_count_after", "label": _("Enabled Policies"), "fieldtype": "Int", "width": 125},
        {"fieldname": "live_posting_allowed_policy_count_after", "label": _("Live Policies"), "fieldtype": "Int", "width": 105},
        {"fieldname": "submitted_journal_entry_count_today", "label": _("JE Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "purchase_invoice_count_today", "label": _("PI Today"), "fieldtype": "Int", "width": 90},
        {"fieldname": "smoke_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_item_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {}

    if filters.get("smoke"):
        conditions.append("i.smoke = %(smoke)s")
        params["smoke"] = filters.get("smoke")

    if filters.get("status"):
        conditions.append("i.status = %(status)s")
        params["status"] = filters.get("status")

    columns = [
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "NDIS Single Guarded Limited Operation Smoke Item", "width": 220},
        {"fieldname": "smoke", "label": _("Smoke"), "fieldtype": "Link", "options": "NDIS Single Guarded Limited Operation Smoke", "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 180},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 340},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 620},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 220},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Data", "width": 240},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            i.name AS item,
            i.smoke,
            i.status,
            i.severity,
            i.category,
            i.check_label,
            i.detail,
            i.source_doctype,
            i.source_name,
            i.checked_on
        FROM `tabNDIS Single Guarded Limited Operation Smoke Item` i
        {build_where(conditions)}
        ORDER BY
            CASE i.status
                WHEN 'Blocker' THEN 1
                WHEN 'Warning' THEN 2
                WHEN 'Pass' THEN 3
                WHEN 'Info' THEN 4
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

    chart = {
        "data": {
            "labels": list(chart_map.keys()),
            "datasets": [{"name": "Items", "values": list(chart_map.values())}],
        },
        "type": "bar",
    }

    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Items"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Pass"]), "indicator": "Green", "label": _("Pass"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Warning"]), "indicator": "Orange", "label": _("Warnings"), "datatype": "Int"},
        {"value": len([row for row in data if row.status == "Blocker"]), "indicator": "Red", "label": _("Blockers"), "datatype": "Int"},
        {"value": len([row for row in data if row.category == "Accounting"]), "indicator": "Red", "label": _("Accounting Rows"), "datatype": "Int"},
    ]

    return columns, data, None, chart, summary


def execute_guardrail_report(filters=None):
    columns, data, message, chart, summary = execute_smoke_report(filters)

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
