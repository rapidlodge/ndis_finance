import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, today

from ndis_finance.services.limited_batch_runtime_guard import assert_limited_batch_runtime_guard
from ndis_finance.services.pe_single_record_draft_smoke import ensure_smoke_bank_account
from ndis_finance.services.permissions import assert_action


SMOKE_ACK = "I_CONFIRM_PHASE10A_RUN_GUARDED_LIMITED_ADAPTER_SMOKE_CREATE_ONE_PAYMENT_ENTRY"
POLICY_DOCTYPE = "NDIS Controlled Production Batch Posting Policy"
SMOKE_DOCTYPE = "NDIS Guarded Limited Adapter Smoke"
ITEM_DOCTYPE = "NDIS Guarded Limited Adapter Smoke Item"


def make_smoke_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-GUARDED-LIMITED-ADAPTER-SMOKE-{timestamp}-{frappe.generate_hash(length=5).upper()}"


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


def set_if_has(doc, fieldname, value):
    if doc.meta.has_field(fieldname):
        setattr(doc, fieldname, value)


def get_flag(doctype, name, fieldname, default=0):
    if not name or not has_column(doctype, fieldname):
        return default
    return int(frappe.db.get_value(doctype, name, fieldname) or 0)


def config_state():
    return {
        "sandbox_enabled": int(frappe.conf.get("ndis_finance_sandbox_posting_enabled") or 0),
        "production_mode": int(frappe.conf.get("ndis_finance_production_mode") or 0),
        "live_pe_enabled": int(frappe.conf.get("ndis_finance_live_payment_entry_posting_enabled") or 0),
    }


def production_batch_enabled_policy_count():
    if not frappe.db.exists("DocType", POLICY_DOCTYPE) or not has_column(POLICY_DOCTYPE, "production_batch_enabled"):
        return 0
    return count_dt(POLICY_DOCTYPE, {"production_batch_enabled": 1})


def live_posting_allowed_policy_count():
    if not frappe.db.exists("DocType", POLICY_DOCTYPE) or not has_column(POLICY_DOCTYPE, "live_posting_allowed"):
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


def latest_activation_gate():
    rows = frappe.get_all(
        "NDIS Limited Batch Adapter Activation Gate",
        filters={
            "status": "Activation Allowed",
            "adapter_activation_allowed": 1,
            "ready_for_guarded_limited_adapter_smoke": 1,
            "smoke_only_allowed": 1,
            "phase9y_hard_block_verified": 1,
            "phase9x_adapter_preview_verified": 1,
            "phase9w_runtime_guard_freeze_verified": 1,
            "phase9v_runtime_guard_verified": 1,
            "controlled_policy_enabled_verified": 1,
            "live_posting_blocked_verified": 1,
            "runtime_guard_active_verified": 1,
            "runtime_validation_ready_verified": 1,
            "direct_adapter_hard_block_verified": 1,
            "adapter_preview_runtime_guard_passed": 1,
            "no_accounting_movement_verified": 1,
            "production_batch_posting_allowed": 0,
            "real_posting_allowed": 0,
            "policy_live_enabled": 0,
            "current_target_policy_enabled": 1,
            "current_target_policy_live": 0,
            "allowed_smoke_batch_line_count": 3,
            "allowed_smoke_payment_entry_count": 1,
            "allowed_smoke_live_posting": 0,
            "allowed_smoke_journal_entry": 0,
            "allowed_smoke_purchase_invoice": 0,
            "actual_payment_entry_created_count": 0,
            "actual_gl_created_count": 0,
            "production_batch_enabled_policy_count": 1,
            "live_posting_allowed_policy_count": 0,
        },
        fields=[
            "name",
            "activation_gate_id",
            "hard_block",
            "adapter_preview",
            "runtime_guard_evidence_freeze",
            "runtime_guard",
            "target_policy_doctype",
            "target_policy",
            "target_policy_name",
            "current_target_policy_enabled",
            "current_target_policy_live",
            "actual_enabled_policy_count",
            "allowed_smoke_batch_line_count",
            "allowed_smoke_batch_amount",
            "allowed_smoke_payment_entry_count",
            "production_batch_enabled_policy_count",
            "live_posting_allowed_policy_count",
            "activation_score",
        ],
        order_by="checked_on desc, creation desc",
        limit=1,
    )
    if not rows:
        return None
    gate = rows[0]
    if flt(gate.allowed_smoke_batch_amount or 0, 2) != 3:
        return None
    return gate


def existing_completed_smoke(activation_gate):
    if not activation_gate:
        return None
    rows = frappe.get_all(
        SMOKE_DOCTYPE,
        filters={
            "activation_gate": activation_gate,
            "status": "Smoke Completed - Rollback Required",
            "adapter_smoke_completed": 1,
            "rollback_required": 1,
        },
        fields=["name", "smoke_id", "payment_entry"],
        limit=1,
    )
    return rows[0] if rows else None


def find_bank_or_cash_account(company):
    rows = frappe.get_all(
        "Account",
        filters={"company": company, "is_group": 0, "account_type": ["in", ["Bank", "Cash"]], "disabled": 0},
        fields=["name", "account_type"],
        order_by="account_type asc, name asc",
        limit=1,
    )
    if rows:
        return rows[0].name
    rows = frappe.get_all(
        "Account",
        filters={"company": company, "is_group": 0, "root_type": "Asset", "disabled": 0},
        fields=["name"],
        order_by="name asc",
        limit=1,
    )
    return rows[0].name if rows else None


def get_candidate_invoices(max_lines=3, max_amount=3):
    invoices = frappe.db.sql(
        """
        SELECT name, company, customer, debit_to, outstanding_amount, grand_total, currency
        FROM `tabSales Invoice`
        WHERE docstatus = 1
          AND outstanding_amount > 0
        ORDER BY posting_date ASC, creation ASC
        LIMIT 100
        """,
        as_dict=True,
    )
    grouped = defaultdict(list)
    for invoice in invoices:
        if invoice.company and invoice.customer and invoice.debit_to:
            grouped[(invoice.company, invoice.customer, invoice.debit_to, invoice.currency)].append(invoice)

    for key, rows in grouped.items():
        selected = []
        remaining = flt(max_amount, 2)
        total = 0
        for row in rows[: int(max_lines or 3)]:
            alloc = min(flt(row.outstanding_amount, 2), remaining)
            if alloc <= 0:
                continue
            selected.append(
                {
                    "sales_invoice": row.name,
                    "outstanding_amount": flt(row.outstanding_amount, 2),
                    "grand_total": flt(row.grand_total, 2),
                    "allocated_amount": flt(alloc, 2),
                    "currency": row.currency,
                }
            )
            total += flt(alloc, 2)
            remaining -= flt(alloc, 2)
            if remaining <= 0:
                break
        if selected and 0 < flt(total, 2) <= flt(max_amount, 2):
            company, customer, debit_to, invoice_currency = key
            paid_to = find_bank_or_cash_account(company)
            if paid_to:
                return {
                    "company": company,
                    "customer": customer,
                    "debit_to": debit_to,
                    "paid_to": paid_to,
                    "currency": invoice_currency,
                    "references": selected,
                    "total_allocated": flt(total, 2),
                    "reference_count": len(selected),
                }
    return None


def validate_source(gate, guard, config, candidate):
    issues = []
    if not config["sandbox_enabled"]:
        issues.append("Sandbox posting config must remain enabled for this guarded smoke.")
    if config["production_mode"]:
        issues.append("Production mode config must remain disabled for Phase 10A.")
    if config["live_pe_enabled"]:
        issues.append("Live Payment Entry posting config must remain disabled for Phase 10A.")
    if not gate:
        issues.append("No Phase 9Z activation gate found.")
        return issues
    existing = existing_completed_smoke(gate.name)
    if existing:
        issues.append(f"Phase 10A smoke already completed for this activation gate: {existing.smoke_id}")
    if not gate.runtime_guard or not frappe.db.exists("NDIS Limited Batch Runtime Guard", gate.runtime_guard):
        issues.append("Linked Phase 9V runtime guard is missing.")
    if not gate.target_policy or not frappe.db.exists(POLICY_DOCTYPE, gate.target_policy):
        issues.append("Linked controlled production batch policy is missing.")
    current_enabled = get_flag(POLICY_DOCTYPE, gate.target_policy, "production_batch_enabled") if gate.target_policy else 0
    current_live = get_flag(POLICY_DOCTYPE, gate.target_policy, "live_posting_allowed") if gate.target_policy else 0
    if current_enabled != 1:
        issues.append("Current target policy production_batch_enabled must be 1 before Phase 10A smoke.")
    if current_live != 0:
        issues.append("Current target policy live_posting_allowed must be 0 before Phase 10A smoke.")
    if int(gate.allowed_smoke_batch_line_count or 0) != 3:
        issues.append("Allowed smoke batch line count must be 3.")
    if flt(gate.allowed_smoke_batch_amount or 0, 2) != 3:
        issues.append("Allowed smoke batch amount must be 3.00.")
    if int(gate.allowed_smoke_payment_entry_count or 0) != 1:
        issues.append("Allowed smoke Payment Entry count must be 1.")
    if guard["production_batch_enabled_policy_count"] != 1:
        issues.append("Exactly one controlled production batch policy must be enabled before Phase 10A smoke.")
    if guard["live_posting_allowed_policy_count"] != 0:
        issues.append("Controlled production live allowed policy count must be 0 before Phase 10A smoke.")
    if guard["submitted_journal_entry_count_today"] != 0:
        issues.append("Submitted Journal Entry today must be 0 before smoke.")
    if guard["purchase_invoice_count_today"] != 0:
        issues.append("Purchase Invoice today must be 0 before smoke.")
    if not candidate:
        issues.append("No suitable submitted Sales Invoice with outstanding amount found for a capped smoke Payment Entry.")
    elif int(candidate["reference_count"] or 0) <= 0 or int(candidate["reference_count"] or 0) > 3:
        issues.append("Candidate reference count must be between 1 and 3.")
    elif flt(candidate["total_allocated"] or 0, 2) <= 0 or flt(candidate["total_allocated"] or 0, 2) > 3:
        issues.append("Candidate total allocation must be greater than 0 and not exceed 3.00.")
    return issues


def run_runtime_guard(candidate):
    if not candidate:
        return {"status": "Skipped", "reason": "No candidate."}
    return assert_limited_batch_runtime_guard(
        batch_line_count=int(candidate["reference_count"] or 0),
        batch_amount=flt(candidate["total_allocated"] or 0, 2),
        payment_entry_count=1,
        live_posting_requested=0,
        allow_journal_entry_side_effect=0,
        allow_purchase_invoice_side_effect=0,
        context="Phase 10A guarded limited adapter smoke",
    )


def create_smoke_payment_entry(candidate, smoke_id, activation_gate=None):
    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

    first_reference = candidate["references"][0]["sales_invoice"]
    pe = get_payment_entry("Sales Invoice", first_reference)
    pe.company = candidate["company"]
    pe.party_type = "Customer"
    pe.party = candidate["customer"]
    pe.posting_date = today()
    pe.paid_from = candidate["debit_to"]
    pe.paid_to = candidate["paid_to"]
    pe.bank_account = ensure_smoke_bank_account(candidate["company"], candidate["paid_to"])
    pe.paid_amount = flt(candidate["total_allocated"], 2)
    pe.received_amount = flt(candidate["total_allocated"], 2)
    pe.reference_no = smoke_id
    pe.reference_date = today()
    pe.remarks = f"Phase 10A guarded limited adapter smoke. Rollback required. Smoke ID: {smoke_id}"
    pe.set("references", [])
    for ref in candidate["references"]:
        pe.append(
            "references",
            {
                "reference_doctype": "Sales Invoice",
                "reference_name": ref["sales_invoice"],
                "allocated_amount": flt(ref["allocated_amount"], 2),
            },
        )
    set_if_has(pe, "custom_ndis_limited_prod_batch_smoke", 1)
    pe.insert(ignore_permissions=True)
    pe.submit()
    return pe.name


def payment_entry_gl_count(payment_entry):
    return count_dt("GL Entry", {"voucher_type": "Payment Entry", "voucher_no": payment_entry}) if payment_entry else 0


def payment_entry_reference_count(payment_entry):
    return count_dt("Payment Entry Reference", {"parent": payment_entry, "parenttype": "Payment Entry"}) if payment_entry else 0


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


def build_pre_items(gate, issues, ack_ok, candidate, runtime_guard_result):
    items = []
    if gate:
        add_item(items, "Pass", "Low", "Evidence", "phase9z_gate_exists", "Phase 9Z activation gate exists", f"Activation gate found: {gate.activation_gate_id}.", "NDIS Limited Batch Adapter Activation Gate", gate.name)
    else:
        add_item(items, "Blocker", "Critical", "Evidence", "phase9z_gate_exists", "Phase 9Z activation gate exists", "No activation gate found.")
    if issues:
        for issue in issues:
            add_item(items, "Blocker", "Critical", "Smoke Source", "smoke_source_valid", "Smoke source valid", issue)
    else:
        add_item(items, "Pass", "Low", "Smoke Source", "smoke_source_valid", "Smoke source valid", "Phase 10A smoke source evidence is valid.")
    if candidate:
        add_item(items, "Pass", "Low", "Candidate", "candidate_found", "Payment Entry candidate found", f"Candidate: {candidate['reference_count']} invoice reference(s), total allocation {candidate['total_allocated']}.")
    else:
        add_item(items, "Blocker", "Critical", "Candidate", "candidate_found", "Payment Entry candidate found", "No suitable candidate found.")
    if runtime_guard_result and runtime_guard_result.get("status") == "Passed":
        add_item(items, "Pass", "Low", "Runtime Guard", "runtime_guard_passed", "Runtime guard passed", "Runtime guard accepted the capped smoke shape.")
    else:
        add_item(items, "Blocker", "Critical", "Runtime Guard", "runtime_guard_passed", "Runtime guard passed", safe_json(runtime_guard_result))
    if ack_ok:
        add_item(items, "Pass", "Low", "Acknowledgement", "ack_ok", "Acknowledgement supplied", "Exact acknowledgement supplied.")
    else:
        add_item(items, "Warning", "Medium", "Acknowledgement", "ack_ok", "Acknowledgement supplied", f"Required acknowledgement not supplied: {SMOKE_ACK}")
    return items


def add_post_items(items, payment_entry, pe_doc, pe_gl_count, pe_ref_count, actual_pe_created, actual_gl_created, guard_before, guard_after):
    if payment_entry and pe_doc and int(pe_doc.docstatus or 0) == 1:
        add_item(items, "Pass", "Low", "Payment Entry", "payment_entry_submitted", "Payment Entry submitted", f"Submitted Payment Entry: {payment_entry}.", "Payment Entry", payment_entry)
    else:
        add_item(items, "Blocker", "Critical", "Payment Entry", "payment_entry_submitted", "Payment Entry submitted", "Payment Entry was not submitted.")
    if 0 < pe_ref_count <= 3:
        add_item(items, "Pass", "Low", "Payment Entry", "reference_count_capped", "Reference count capped", f"Reference count is {pe_ref_count}.")
    else:
        add_item(items, "Blocker", "Critical", "Payment Entry", "reference_count_capped", "Reference count capped", f"Reference count is {pe_ref_count}.")
    if pe_doc and 0 < flt(pe_doc.paid_amount or 0, 2) <= 3:
        add_item(items, "Pass", "Low", "Payment Entry", "amount_capped", "Amount capped", f"Payment Entry amount is {flt(pe_doc.paid_amount, 2)}.")
    else:
        add_item(items, "Blocker", "Critical", "Payment Entry", "amount_capped", "Amount capped", "Payment Entry amount failed cap check.")
    if pe_gl_count > 0:
        add_item(items, "Pass", "Low", "GL", "payment_entry_gl_created", "Payment Entry GL created", f"Payment Entry GL row count is {pe_gl_count}.")
    else:
        add_item(items, "Blocker", "Critical", "GL", "payment_entry_gl_created", "Payment Entry GL created", "No Payment Entry GL rows found.")
    if actual_pe_created == 1:
        add_item(items, "Pass", "Low", "Guardrail", "actual_pe_delta", "Actual PE delta is 1", "Exactly one Payment Entry was created.")
    else:
        add_item(items, "Blocker", "Critical", "Guardrail", "actual_pe_delta", "Actual PE delta is 1", f"Payment Entry delta is {actual_pe_created}.")
    if actual_gl_created == pe_gl_count and actual_gl_created > 0:
        add_item(items, "Pass", "Low", "Guardrail", "actual_gl_delta", "Actual GL delta matches PE", f"Payment Entry GL delta is {actual_gl_created}.")
    else:
        add_item(items, "Blocker", "Critical", "Guardrail", "actual_gl_delta", "Actual GL delta matches PE", f"GL delta {actual_gl_created}; linked PE GL rows {pe_gl_count}.")
    if guard_after["submitted_journal_entry_count_today"] == guard_before["submitted_journal_entry_count_today"]:
        add_item(items, "Pass", "Low", "Guardrail", "no_journal_entry", "No Journal Entry created", "Submitted Journal Entry count stayed unchanged.")
    else:
        add_item(items, "Blocker", "Critical", "Guardrail", "no_journal_entry", "No Journal Entry created", "Submitted Journal Entry count changed.")
    if guard_after["purchase_invoice_count_today"] == guard_before["purchase_invoice_count_today"]:
        add_item(items, "Pass", "Low", "Guardrail", "no_purchase_invoice", "No Purchase Invoice created", "Purchase Invoice count stayed unchanged.")
    else:
        add_item(items, "Blocker", "Critical", "Guardrail", "no_purchase_invoice", "No Purchase Invoice created", "Purchase Invoice count changed.")


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
        row = frappe.new_doc(ITEM_DOCTYPE)
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


def build_base_result(gate, config, guard_before, candidate, ack_ok, issues, runtime_guard_result, items, item_summary, pre_score, dry_run):
    return {
        "dry_run": bool(int(dry_run or 0)),
        "status": "Needs Review",
        "smoke_status": "Needs Review",
        "adapter_smoke_completed": 0,
        "rollback_required": 0,
        "freeze_required_after_rollback": 0,
        "ready_for_adapter_smoke_rollback": 0,
        "phase9z_activation_gate_verified": 1 if gate else 0,
        "phase9y_hard_block_verified": 1 if gate else 0,
        "phase9x_adapter_preview_verified": 1 if gate else 0,
        "phase9w_runtime_guard_freeze_verified": 1 if gate else 0,
        "phase9v_runtime_guard_verified": 1 if gate else 0,
        "controlled_policy_enabled_verified": 1 if gate else 0,
        "live_posting_blocked_verified": 1 if gate else 0,
        "runtime_guard_active_verified": 1 if gate else 0,
        "runtime_validation_ready_verified": 1 if gate else 0,
        "runtime_guard_passed": 1 if runtime_guard_result and runtime_guard_result.get("status") == "Passed" else 0,
        "activation_gate": gate.name if gate else None,
        "hard_block": gate.hard_block if gate else None,
        "adapter_preview": gate.adapter_preview if gate else None,
        "runtime_guard_evidence_freeze": gate.runtime_guard_evidence_freeze if gate else None,
        "runtime_guard": gate.runtime_guard if gate else None,
        "target_policy_doctype": POLICY_DOCTYPE,
        "target_policy": gate.target_policy if gate else None,
        "target_policy_name": gate.target_policy_name if gate else None,
        "current_target_policy_enabled": get_flag(POLICY_DOCTYPE, gate.target_policy, "production_batch_enabled") if gate else 0,
        "current_target_policy_live": get_flag(POLICY_DOCTYPE, gate.target_policy, "live_posting_allowed") if gate else 0,
        "actual_enabled_policy_count": int(gate.actual_enabled_policy_count or 0) if gate else 0,
        "company": candidate.get("company") if candidate else None,
        "customer": candidate.get("customer") if candidate else None,
        "paid_from_account": candidate.get("debit_to") if candidate else None,
        "paid_to_account": candidate.get("paid_to") if candidate else None,
        "allowed_smoke_batch_line_count": 3,
        "allowed_smoke_batch_amount": 3,
        "allowed_smoke_payment_entry_count": 1,
        "actual_smoke_batch_line_count": int(candidate.get("reference_count") or 0) if candidate else 0,
        "actual_smoke_batch_amount": flt(candidate.get("total_allocated") or 0, 2) if candidate else 0,
        "actual_smoke_payment_entry_count": 0,
        "payment_entry_count_before": guard_before["payment_entry_count"],
        "payment_entry_count_after": guard_before["payment_entry_count"],
        "payment_entry_gl_count_before": guard_before["payment_entry_gl_count"],
        "payment_entry_gl_count_after": guard_before["payment_entry_gl_count"],
        "submitted_journal_entry_count_today": guard_before["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_before["purchase_invoice_count_today"],
        "production_batch_enabled_policy_count": guard_before["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count": guard_before["live_posting_allowed_policy_count"],
        "actual_payment_entry_created_count": 0,
        "actual_gl_created_count": 0,
        "payment_entry": None,
        "payment_entry_docstatus": 0,
        "payment_entry_status": None,
        "payment_entry_amount": 0,
        "payment_entry_reference_count": 0,
        "payment_entry_gl_count": 0,
        "smoke_score": pre_score,
        **item_summary,
        "items": items,
        "issues": issues,
        "candidate": candidate,
        "runtime_guard_result": runtime_guard_result,
        "guardrails_before": guard_before,
        "config": config,
        "required_acknowledgement": SMOKE_ACK,
        "acknowledgement_ok": ack_ok,
        "note": "Phase 10A guarded limited adapter smoke. Exact acknowledgement creates one submitted Payment Entry and requires rollback.",
    }


@frappe.whitelist()
def run_guarded_limited_adapter_smoke(dry_run=1, acknowledgement=None, notes=None):
    assert_action("run_guarded_limited_adapter_smoke")
    gate = latest_activation_gate()
    config = config_state()
    guard_before = guardrails()
    candidate = get_candidate_invoices(max_lines=3, max_amount=3)
    ack_ok = acknowledgement == SMOKE_ACK
    issues = validate_source(gate, guard_before, config, candidate)
    runtime_guard_result = None
    if candidate and not issues:
        try:
            runtime_guard_result = run_runtime_guard(candidate)
        except Exception as exc:
            runtime_guard_result = {"status": "Failed", "error": str(exc)}
            issues.append(f"Runtime guard failed: {exc}")
    items = build_pre_items(gate, issues, ack_ok, candidate, runtime_guard_result)
    item_summary = summarise_items(items)
    pre_score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    allowed = int(ack_ok and item_summary["blocker_count"] == 0 and bool(gate) and bool(candidate) and runtime_guard_result and runtime_guard_result.get("status") == "Passed")
    base_result = build_base_result(gate, config, guard_before, candidate, ack_ok, issues, runtime_guard_result, items, item_summary, pre_score, dry_run)

    if int(dry_run or 0):
        return {**base_result, "guardrails_after": guardrails()}

    if not allowed:
        doc = frappe.new_doc(SMOKE_DOCTYPE)
        doc.smoke_id = make_smoke_id()
        for fieldname, value in base_result.items():
            if doc.meta.has_field(fieldname):
                setattr(doc, fieldname, value)
        doc.site_name = frappe.local.site
        doc.sandbox_config_enabled = config["sandbox_enabled"]
        doc.production_mode_detected = config["production_mode"]
        doc.live_payment_entry_posting_config = config["live_pe_enabled"]
        doc.checked_on = now_datetime()
        doc.checked_by = frappe.session.user
        doc.required_acknowledgement = SMOKE_ACK
        doc.acknowledgement = acknowledgement
        doc.acknowledgement_ok = int(ack_ok)
        doc.summary_json = safe_json(base_result)
        doc.notes = notes
        doc.insert(ignore_permissions=True)
        create_items(doc, items)
        frappe.db.commit()
        return {**base_result, "created": True, "smoke": doc.name, "smoke_id": doc.smoke_id, "guardrails_after": guardrails()}

    smoke_id = make_smoke_id()
    payment_entry = create_smoke_payment_entry(candidate, smoke_id, gate.name)
    pe_doc = frappe.get_doc("Payment Entry", payment_entry)
    pe_gl_count = payment_entry_gl_count(payment_entry)
    pe_ref_count = payment_entry_reference_count(payment_entry)
    guard_after = guardrails()
    actual_pe_created = guard_after["payment_entry_count"] - guard_before["payment_entry_count"]
    actual_gl_created = guard_after["payment_entry_gl_count"] - guard_before["payment_entry_gl_count"]
    add_post_items(items, payment_entry, pe_doc, pe_gl_count, pe_ref_count, actual_pe_created, actual_gl_created, guard_before, guard_after)
    item_summary = summarise_items(items)
    score = calculate_score(item_summary["blocker_count"], item_summary["warning_count"])
    completed = int(item_summary["blocker_count"] == 0)
    result = {
        **base_result,
        "status": "Smoke Completed - Rollback Required" if completed else "Blocked",
        "smoke_status": "Guarded Limited Adapter Smoke Completed" if completed else "Blocked",
        "adapter_smoke_completed": completed,
        "rollback_required": completed,
        "freeze_required_after_rollback": completed,
        "ready_for_adapter_smoke_rollback": completed,
        "payment_entry_submitted_verified": 1 if int(pe_doc.docstatus or 0) == 1 else 0,
        "payment_entry_gl_created_verified": 1 if pe_gl_count > 0 else 0,
        "no_journal_entry_verified": 1 if guard_after["submitted_journal_entry_count_today"] == guard_before["submitted_journal_entry_count_today"] else 0,
        "no_purchase_invoice_verified": 1 if guard_after["purchase_invoice_count_today"] == guard_before["purchase_invoice_count_today"] else 0,
        "payment_entry": payment_entry,
        "payment_entry_docstatus": int(pe_doc.docstatus or 0),
        "payment_entry_status": pe_doc.status,
        "payment_entry_amount": flt(pe_doc.paid_amount or 0, 2),
        "payment_entry_reference_count": pe_ref_count,
        "payment_entry_gl_count": pe_gl_count,
        "actual_smoke_payment_entry_count": actual_pe_created,
        "payment_entry_count_after": guard_after["payment_entry_count"],
        "payment_entry_gl_count_after": guard_after["payment_entry_gl_count"],
        "actual_payment_entry_created_count": actual_pe_created,
        "actual_gl_created_count": actual_gl_created,
        "submitted_journal_entry_count_today": guard_after["submitted_journal_entry_count_today"],
        "purchase_invoice_count_today": guard_after["purchase_invoice_count_today"],
        "production_batch_enabled_policy_count": guard_after["production_batch_enabled_policy_count"],
        "live_posting_allowed_policy_count": guard_after["live_posting_allowed_policy_count"],
        "smoke_score": score,
        **item_summary,
        "items": items,
        "guardrails_after": guard_after,
    }
    doc = frappe.new_doc(SMOKE_DOCTYPE)
    doc.smoke_id = smoke_id
    for fieldname, value in result.items():
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, value)
    doc.site_name = frappe.local.site
    doc.sandbox_config_enabled = config["sandbox_enabled"]
    doc.production_mode_detected = config["production_mode"]
    doc.live_payment_entry_posting_config = config["live_pe_enabled"]
    doc.checked_on = now_datetime()
    doc.checked_by = frappe.session.user
    doc.required_acknowledgement = SMOKE_ACK
    doc.acknowledgement = acknowledgement
    doc.acknowledgement_ok = int(ack_ok)
    doc.summary_json = safe_json(result)
    doc.notes = notes
    doc.insert(ignore_permissions=True)
    create_items(doc, items)
    frappe.db.commit()
    return {**result, "created": True, "smoke": doc.name, "smoke_id": doc.smoke_id}


@frappe.whitelist()
def cancel_guarded_limited_adapter_smoke_audit(smoke, reason=None):
    assert_action("cancel_guarded_limited_adapter_smoke_audit")
    if not frappe.db.exists(SMOKE_DOCTYPE, smoke):
        frappe.throw(_("Smoke audit not found: {0}").format(smoke))
    doc = frappe.get_doc(SMOKE_DOCTYPE, smoke)
    if doc.status == "Cancelled":
        return {"smoke": smoke, "status": "Cancelled", "note": "Already cancelled."}
    if int(doc.adapter_smoke_completed or 0) or doc.payment_entry:
        frappe.throw(_("Cannot cancel a completed Phase 10A smoke. Run the rollback phase instead."))
    frappe.db.set_value(
        SMOKE_DOCTYPE,
        smoke,
        {
            "status": "Cancelled",
            "smoke_status": "Cancelled",
            "adapter_smoke_completed": 0,
            "rollback_required": 0,
            "freeze_required_after_rollback": 0,
            "ready_for_adapter_smoke_rollback": 0,
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "summary_json": reason or "Phase 10A no-ack smoke audit cancelled.",
        },
        update_modified=False,
    )
    frappe.db.sql(f"UPDATE `tab{ITEM_DOCTYPE}` SET status = 'Cancelled' WHERE smoke = %(smoke)s", {"smoke": smoke})
    frappe.db.commit()
    return {"smoke": smoke, "status": "Cancelled", "note": "No-ack smoke audit cancelled only. No policy or accounting movement occurred."}


@frappe.whitelist()
def quick_guarded_limited_adapter_smoke_summary(limit=20):
    smokes = frappe.get_all(
        SMOKE_DOCTYPE,
        fields=[
            "name",
            "smoke_id",
            "status",
            "smoke_status",
            "adapter_smoke_completed",
            "rollback_required",
            "freeze_required_after_rollback",
            "ready_for_adapter_smoke_rollback",
            "activation_gate",
            "runtime_guard",
            "target_policy",
            "company",
            "customer",
            "payment_entry",
            "payment_entry_docstatus",
            "payment_entry_amount",
            "payment_entry_reference_count",
            "payment_entry_gl_count",
            "actual_payment_entry_created_count",
            "actual_gl_created_count",
            "production_batch_enabled_policy_count",
            "live_posting_allowed_policy_count",
            "smoke_score",
            "checked_on",
            "checked_by",
        ],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    items = frappe.get_all(
        ITEM_DOCTYPE,
        fields=["name", "smoke", "status", "severity", "category", "check_label", "detail", "source_doctype", "source_name"],
        order_by="creation desc",
        limit=int(limit or 20),
    )
    return {"smokes": smokes, "items": items, "required_acknowledgement": SMOKE_ACK, "guardrails": guardrails(), "note": "Phase 10A guarded limited adapter smoke summary. Completed smoke requires rollback."}


def smoke_columns():
    return [
        {"fieldname": "smoke", "label": _("Smoke"), "fieldtype": "Link", "options": SMOKE_DOCTYPE, "width": 220},
        {"fieldname": "smoke_id", "label": _("Smoke ID"), "fieldtype": "Data", "width": 430},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 190},
        {"fieldname": "smoke_status", "label": _("Smoke Status"), "fieldtype": "Data", "width": 280},
        {"fieldname": "adapter_smoke_completed", "label": _("Completed"), "fieldtype": "Check", "width": 90},
        {"fieldname": "rollback_required", "label": _("Rollback Required"), "fieldtype": "Check", "width": 120},
        {"fieldname": "activation_gate", "label": _("Phase 9Z Gate"), "fieldtype": "Link", "options": "NDIS Limited Batch Adapter Activation Gate", "width": 220},
        {"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link", "options": "Payment Entry", "width": 180},
        {"fieldname": "payment_entry_docstatus", "label": _("PE Docstatus"), "fieldtype": "Int", "width": 100},
        {"fieldname": "payment_entry_amount", "label": _("PE Amount"), "fieldtype": "Currency", "options": "currency", "width": 110},
        {"fieldname": "payment_entry_reference_count", "label": _("PE Refs"), "fieldtype": "Int", "width": 90},
        {"fieldname": "payment_entry_gl_count", "label": _("PE GL Rows"), "fieldtype": "Int", "width": 100},
        {"fieldname": "actual_payment_entry_created_count", "label": _("Actual PE"), "fieldtype": "Int", "width": 90},
        {"fieldname": "actual_gl_created_count", "label": _("Actual GL"), "fieldtype": "Int", "width": 90},
        {"fieldname": "production_batch_enabled_policy_count", "label": _("Enabled Policies"), "fieldtype": "Int", "width": 120},
        {"fieldname": "live_posting_allowed_policy_count", "label": _("Live Policies"), "fieldtype": "Int", "width": 110},
        {"fieldname": "smoke_score", "label": _("Score"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


def execute_smoke_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions = []
    params = {"currency": currency()}
    if filters.get("status"):
        conditions.append("s.status = %(status)s")
        params["status"] = filters.get("status")
    data = frappe.db.sql(
        f"""
        SELECT
            s.name AS smoke, s.smoke_id, s.status, s.smoke_status, s.adapter_smoke_completed,
            s.rollback_required, s.activation_gate, s.payment_entry, s.payment_entry_docstatus,
            s.payment_entry_amount, s.payment_entry_reference_count, s.payment_entry_gl_count,
            s.actual_payment_entry_created_count, s.actual_gl_created_count,
            s.production_batch_enabled_policy_count, s.live_posting_allowed_policy_count,
            s.smoke_score, s.checked_on, %(currency)s AS currency
        FROM `tab{SMOKE_DOCTYPE}` s
        {build_where(conditions)}
        ORDER BY s.creation DESC
        """,
        params,
        as_dict=True,
    )
    chart = {"data": {"labels": [row.smoke_id for row in data[:20]], "datasets": [{"name": "Actual PE Created", "values": [int(row.actual_payment_entry_created_count or 0) for row in data[:20]]}, {"name": "Rollback Required", "values": [int(row.rollback_required or 0) for row in data[:20]]}]}, "type": "bar"}
    summary = [
        {"value": len(data), "indicator": "Blue", "label": _("Smokes"), "datatype": "Int"},
        {"value": sum(int(row.adapter_smoke_completed or 0) for row in data), "indicator": "Green", "label": _("Completed"), "datatype": "Int"},
        {"value": sum(int(row.rollback_required or 0) for row in data), "indicator": "Orange", "label": _("Rollback Required"), "datatype": "Int"},
        {"value": sum(int(row.actual_payment_entry_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual PE"), "datatype": "Int"},
        {"value": sum(int(row.actual_gl_created_count or 0) for row in data), "indicator": "Red", "label": _("Actual GL"), "datatype": "Int"},
    ]
    return smoke_columns(), data, None, chart, summary


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
        {"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": ITEM_DOCTYPE, "width": 220},
        {"fieldname": "smoke", "label": _("Smoke"), "fieldtype": "Link", "options": SMOKE_DOCTYPE, "width": 220},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 100},
        {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 170},
        {"fieldname": "check_label", "label": _("Check"), "fieldtype": "Data", "width": 320},
        {"fieldname": "detail", "label": _("Detail"), "fieldtype": "Small Text", "width": 560},
        {"fieldname": "source_doctype", "label": _("Source DocType"), "fieldtype": "Data", "width": 220},
        {"fieldname": "source_name", "label": _("Source Name"), "fieldtype": "Data", "width": 240},
        {"fieldname": "checked_on", "label": _("Checked On"), "fieldtype": "Datetime", "width": 170},
    ]
    data = frappe.db.sql(
        f"""
        SELECT i.name AS item, i.smoke, i.status, i.severity, i.category, i.check_label,
            i.detail, i.source_doctype, i.source_name, i.checked_on
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
    columns, data, message, chart, summary = execute_smoke_report(filters)
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
