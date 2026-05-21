import frappe
from frappe import _


ACTION_ROLE_MAP = {
    "create_claim_batch": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
        "NDIS Claims Officer",
    ],
    "submit_claim_batch": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
        "NDIS Claims Officer",
    ],
    "record_claim_outcome": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
        "NDIS Claims Officer",
    ],
    "create_payment_reconciliation": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
        "NDIS Claims Officer",
    ],
    "record_payment_outcome": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
        "NDIS Claims Officer",
    ],
    "import_remittance": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
        "NDIS Claims Officer",
    ],
    "match_remittance": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
        "NDIS Claims Officer",
    ],
    "apply_remittance": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
        "NDIS Claims Officer",
    ],
    "generate_claim_export": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
        "NDIS Claims Officer",
    ],
    "cancel_claim_export": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "manage_claim_export_template": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
        "NDIS Catalogue Manager",
    ],
    "manage_cost_pool": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "allocate_cost_pool": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "cancel_cost_pool": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "import_payroll_costs": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "cancel_payroll_cost_import": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "create_executive_snapshot": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
        "NDIS Automation Manager",
    ],
    "cancel_executive_snapshot": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "manage_executive_exception_rule": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "evaluate_executive_exceptions": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
        "NDIS Automation Manager",
    ],
    "resolve_executive_exception_alert": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "manage_executive_action_plan": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "update_executive_action_plan": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
        "NDIS Finance Officer",
    ],
    "complete_executive_action_plan": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "cancel_executive_action_plan": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "create_governance_pack": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "signoff_governance_pack": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_governance_pack": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "run_production_readiness_check": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "acknowledge_production_readiness": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_production_readiness_check": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "manage_accounting_posting_policy": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "create_accounting_posting_preview": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
        "NDIS Finance Officer",
    ],
    "cancel_accounting_posting_preview": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "create_accounting_posting_request": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
        "NDIS Finance Officer",
    ],
    "approve_accounting_posting_request": [
        "System Manager",
        "NDIS CFO",
    ],
    "reject_accounting_posting_request": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "dry_run_accounting_posting_request": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "cancel_accounting_posting_request": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "create_sandbox_journal_entry_draft": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_sandbox_accounting_posting_run": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "run_sandbox_accounting_cleanup": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_sandbox_accounting_cleanup": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "run_accounting_sandbox_completion_gate": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "cancel_accounting_sandbox_completion_gate": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "manage_accounting_design_matrix": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "run_accounting_design_review": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "cancel_accounting_design_review": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "manage_payment_entry_mapping_rule": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "run_payment_entry_allocation_preview": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
        "NDIS Finance Officer",
    ],
    "cancel_payment_entry_allocation_preview": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "create_sandbox_payment_entry_draft": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_sandbox_payment_entry_run": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "create_recovery_case": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
        "NDIS Recovery Officer",
    ],
    "add_recovery_activity": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
        "NDIS Recovery Officer",
        "NDIS Finance Officer",
    ],
    "escalate_recovery_case": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
        "NDIS Recovery Officer",
    ],
    "resolve_recovery_case": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
        "NDIS Recovery Officer",
    ],
    "close_recovery_case": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
        "NDIS Recovery Officer",
    ],
    "write_off_recovery_case": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
        "NDIS Write Off Approver",
    ],
    "create_email_draft": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
        "NDIS Recovery Officer",
        "NDIS Finance Officer",
    ],
    "approve_email_draft": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
        "NDIS Communication Approver",
    ],
    "mark_email_sent_manually": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
        "NDIS Recovery Officer",
        "NDIS Communication Approver",
    ],
    "cancel_email_draft": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
        "NDIS Recovery Officer",
        "NDIS Communication Approver",
    ],
    "run_recovery_automation": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
        "NDIS Automation Manager",
    ],
    "manage_catalogue": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
        "NDIS Catalogue Manager",
    ],
    "manage_budget": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
        "NDIS Budget Manager",
    ],
}


def get_user_roles(user=None):
    user = user or frappe.session.user

    if user == "Administrator":
        return ["Administrator", "System Manager"]

    return frappe.get_roles(user)


def has_any_role(allowed_roles, user=None):
    user_roles = set(get_user_roles(user))
    allowed_roles = set(allowed_roles or [])

    if "Administrator" in user_roles:
        return True

    return bool(user_roles.intersection(allowed_roles))


def assert_action(action, user=None):
    allowed_roles = ACTION_ROLE_MAP.get(action)

    if not allowed_roles:
        frappe.throw(
            _("NDIS permission action is not configured: {0}").format(action),
            frappe.PermissionError,
        )

    if not has_any_role(allowed_roles, user=user):
        frappe.throw(
            _(
                "You do not have permission to perform this NDIS Finance action: {0}. "
                "Required role: {1}"
            ).format(action, ", ".join(allowed_roles)),
            frappe.PermissionError,
        )

    return True


@frappe.whitelist()
def permission_matrix():
    return {
        action: {
            "allowed_roles": roles,
            "current_user_allowed": has_any_role(roles),
        }
        for action, roles in ACTION_ROLE_MAP.items()
    }
