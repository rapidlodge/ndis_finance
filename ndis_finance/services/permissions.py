import frappe
from frappe import _


ACTION_ROLE_MAP = {
    # Phase 11N post-closeout steady-state baseline controls
    "run_post_closeout_steady_state_baseline": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_post_closeout_steady_state_baseline_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 11M next governed limited operation closeout controls
    "run_next_governed_limited_operation_closeout": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_next_governed_limited_operation_closeout_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 11L next governed limited operation rollback freeze controls
    "run_next_governed_limited_operation_rollback_freeze": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_next_governed_limited_operation_rollback_freeze_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 11K next governed limited operation smoke rollback controls
    "run_next_governed_limited_operation_smoke_rollback": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_next_governed_limited_operation_smoke_rollback_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 11J next governed limited operation smoke execution controls
    "run_next_governed_limited_operation_smoke": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_next_governed_limited_operation_smoke_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

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
    # Phase 11I next governed limited operation execution gate controls
    "run_next_governed_limited_operation_execution_gate": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_next_governed_limited_operation_execution_gate_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 11H next governed limited operation preview controls
    "run_next_governed_limited_operation_preview": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_next_governed_limited_operation_preview_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 11G next governed limited operation candidate validation controls
    "run_next_governed_limited_operation_candidate_validation": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_next_governed_limited_operation_candidate_validation_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 11F next governed limited operation candidate selection controls
    "run_next_governed_limited_operation_candidate_selection": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_next_governed_limited_operation_candidate_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 11E next governed limited operation design controls
    "run_next_governed_limited_operation_design": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_next_governed_limited_operation_design_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 11D next governed limited operation planning controls
    "run_next_governed_limited_operation_planning": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_next_governed_limited_operation_planning_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 11C next governed limited operation precheck controls
    "run_next_governed_limited_operation_precheck": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_next_governed_limited_operation_precheck_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 11B governed steady-state runtime monitor controls
    "run_governed_steady_state_monitor": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_governed_steady_state_monitor_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 11A governed steady-state continuation baseline controls
    "run_governed_steady_state_baseline": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_governed_steady_state_baseline_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 10Z governed limited operation closeout controls
    "run_governed_limited_operation_closeout": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_governed_limited_operation_closeout_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 10Y governed limited operation smoke rollback freeze controls
    "run_governed_limited_operation_smoke_freeze": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_governed_limited_operation_smoke_freeze_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 10X governed limited operation smoke rollback controls
    "run_governed_limited_operation_smoke_rollback": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_governed_limited_operation_smoke_rollback_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 10W governed limited operation smoke execution controls
    "run_governed_limited_operation_smoke": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_governed_limited_operation_smoke_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 10V governed limited operation execution gate controls
    "run_governed_limited_operation_execution_gate": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_governed_limited_operation_execution_gate_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 10U governed limited operation preview controls
    "run_governed_limited_operation_preview": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_governed_limited_operation_preview_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 10T governed limited operation pre-execution gate controls
    "run_governed_limited_op_pre_execution_gate": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_governed_limited_op_pre_execution_gate_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 10S governed controlled limited operations readiness controls
    "run_governed_limited_ops_readiness": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_governed_limited_ops_readiness_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 10R runtime watch governance closeout controls
    "run_runtime_watch_governance_closeout": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_runtime_watch_governance_closeout_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 10Q runtime watch violation simulation freeze controls
    "run_runtime_watch_violation_simulation_freeze": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_runtime_watch_violation_simulation_freeze_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 10P runtime watch violation simulation controls
    "run_runtime_watch_violation_simulation": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_runtime_watch_violation_simulation_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 10O controlled limited operations runtime watch controls
    "run_controlled_limited_operations_runtime_watch": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_controlled_limited_operations_runtime_watch_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 10N controlled limited operations steady-state baseline controls
    "run_controlled_limited_operations_steady_state_baseline": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_controlled_limited_operations_steady_state_baseline_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 10M final limited operation closeout gate controls
    "run_limited_operation_closeout_gate": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_limited_operation_closeout_gate_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 10L single guarded operation smoke rollback freeze controls
    "run_single_guarded_operation_smoke_rollback_freeze": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_single_guarded_operation_smoke_rollback_freeze_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 10K single guarded limited operation smoke rollback controls
    "run_single_guarded_limited_operation_smoke_rollback": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_single_guarded_limited_operation_smoke_rollback_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 10J single guarded limited operation smoke execution controls
    "run_single_guarded_limited_operation_smoke": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_single_guarded_limited_operation_smoke_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 10I guarded limited operation execution gate controls
    "run_guarded_limited_operation_execution_gate": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_guarded_limited_operation_execution_gate_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 10H guarded limited operation preview controls
    "run_guarded_limited_operation_preview": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_guarded_limited_operation_preview_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 10G pre-operation monitoring check controls
    "run_controlled_limited_operation_pre_check": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_controlled_limited_operation_pre_check_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 10F controlled limited operations monitoring register controls
    "run_controlled_limited_operations_monitoring_register": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_controlled_limited_operations_monitoring_register_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 10E final guarded adapter policy decision controls
    "run_guarded_adapter_final_policy_decision_keep_enabled": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_guarded_adapter_final_policy_decision_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 10D final guarded adapter policy review controls
    "run_guarded_adapter_final_policy_review": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_guarded_adapter_final_policy_review_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 10C guarded limited adapter smoke rollback freeze controls
    "run_guarded_adapter_smoke_rollback_freeze": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_guarded_adapter_smoke_rollback_freeze_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 10B guarded limited adapter smoke rollback controls
    "run_guarded_limited_adapter_smoke_rollback": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_guarded_limited_adapter_smoke_rollback_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 10A guarded limited adapter smoke controls
    "run_guarded_limited_adapter_smoke": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_guarded_limited_adapter_smoke_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 9Z guarded limited adapter activation gate controls
    "run_limited_batch_adapter_activation_gate": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_limited_batch_adapter_activation_gate": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 9Y guarded limited batch posting adapter hard-block controls
    "run_limited_batch_posting_adapter_hard_block": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_limited_batch_posting_adapter_hard_block": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 9X controlled limited batch posting adapter preview controls
    "run_limited_batch_posting_adapter_preview": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_limited_batch_posting_adapter_preview": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 9W controlled limited batch runtime guard evidence freeze controls
    "run_limited_batch_runtime_guard_evidence_freeze": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_limited_batch_runtime_guard_evidence_freeze": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 9V controlled limited batch runtime guard controls
    "run_limited_batch_runtime_guard": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_limited_batch_runtime_guard": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "simulate_limited_batch_runtime_guard": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 9U limited production batch use monitor gate controls
    "run_limited_production_batch_use_monitor_gate": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_limited_production_batch_use_monitor_gate": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 9T controlled limited production batch policy enablement freeze controls
    "run_limited_production_batch_policy_enablement_freeze": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_limited_production_batch_policy_enablement_freeze": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 9S controlled limited production batch policy enablement controls
    "run_limited_production_batch_policy_enablement": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_limited_production_batch_policy_enablement": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 9R limited production batch enablement readiness gate controls
    "run_limited_production_batch_enablement_readiness_gate": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_limited_production_batch_enablement_readiness_gate": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 9Q limited production batch enablement evidence freeze controls
    "run_limited_production_batch_enablement_freeze": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_limited_production_batch_enablement_freeze": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 9P limited controlled enablement smoke rollback controls
    "run_limited_production_batch_enablement_rollback": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_limited_production_batch_enablement_rollback": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 9O limited controlled enablement smoke controls
    "run_limited_production_batch_enablement_smoke": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_limited_production_batch_enablement_smoke": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 9N limited production batch enablement activation gate controls
    "run_limited_production_batch_enablement_activation_gate": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_limited_production_batch_enablement_activation_gate": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 9M limited production batch enablement hard-block adapter controls
    "run_limited_production_batch_enablement_adapter": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_limited_production_batch_enablement_adapter": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "direct_limited_production_batch_policy_enablement": [
        "System Manager",
        "NDIS CFO",
    ],

    # Phase 9L limited production batch enablement preview controls
    "run_limited_production_batch_enablement_preview": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_limited_production_batch_enablement_preview": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 9K limited production batch enablement design gate controls
    "run_limited_production_batch_enablement_design_gate": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_limited_production_batch_enablement_design_gate": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 9J limited production batch policy lock controls
    "run_limited_production_batch_policy_lock": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_limited_production_batch_policy_lock": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 9I limited production batch policy finalisation gate controls
    "run_limited_production_batch_policy_finalisation_gate": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_limited_production_batch_policy_finalisation_gate": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 9H limited production batch smoke evidence freeze controls
    "run_limited_production_batch_smoke_evidence_freeze": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_limited_production_batch_smoke_evidence_freeze": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 9G limited production batch smoke rollback controls
    "run_limited_production_batch_smoke_rollback": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_limited_production_batch_smoke_rollback_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 9F limited production batch controlled smoke controls
    "run_limited_production_batch_controlled_smoke": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_limited_production_batch_controlled_smoke_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 9E limited production batch activation gate controls
    "run_limited_production_batch_activation_gate": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_limited_production_batch_activation_gate": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 9D limited production batch hard-block adapter controls
    "run_limited_production_batch_hard_block_adapter": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_limited_production_batch_hard_block_adapter": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "attempt_limited_production_batch_live_creation": [
        "System Manager",
        "NDIS CFO",
    ],

    # Phase 9C limited production batch policy preview controls
    "run_limited_production_batch_policy_preview": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_limited_production_batch_policy_preview": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 9B limited production batch policy design controls
    "run_limited_production_batch_policy_design": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_limited_production_batch_policy_design": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 9A controlled production batch policy review gate controls
    "run_controlled_production_batch_policy_review_gate": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_controlled_production_batch_policy_review_gate": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 8G controlled production batch smoke evidence freeze controls
    "run_controlled_production_batch_smoke_evidence_freeze": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_controlled_production_batch_smoke_evidence_freeze": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 8F controlled production batch smoke rollback controls
    "run_controlled_production_batch_smoke_rollback": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_controlled_production_batch_smoke_rollback_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 8E single controlled production batch smoke controls
    "run_controlled_production_batch_smoke": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_controlled_production_batch_smoke_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 8D controlled production batch activation gate controls
    "run_controlled_production_batch_activation_gate": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_controlled_production_batch_activation_gate": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 8C controlled production batch hard-block adapter controls
    "run_controlled_production_batch_adapter": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_controlled_production_batch_adapter": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 8B controlled production batch posting preview controls
    "run_controlled_production_batch_preview": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_controlled_production_batch_preview": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 8A controlled production batch posting design gate controls
    "run_controlled_production_batch_design_gate": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_controlled_production_batch_design_gate": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 7H controlled batch PE rollback evidence freeze controls
    "run_real_remittance_batch_pe_freeze": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_real_remittance_batch_pe_freeze": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 7G controlled batch Payment Entry rollback controls
    "run_real_remittance_batch_pe_rollback": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_real_remittance_batch_pe_rollback": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 7F controlled real remittance batch Payment Entry smoke controls
    "run_real_remittance_batch_pe_smoke": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_real_remittance_batch_pe_smoke": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 7E controlled batch smoke source harness controls
    "run_real_remittance_batch_source_harness": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "cancel_real_remittance_batch_source_harness": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 7D real remittance batch activation gate controls
    "run_real_remittance_batch_activation_gate": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_real_remittance_batch_activation_gate": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 7C real remittance batch hard-block adapter controls
    "run_real_remittance_batch_adapter": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "cancel_real_remittance_batch_adapter": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 7B real remittance batch posting preview controls
    "run_real_remittance_batch_preview": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "cancel_real_remittance_batch_preview": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 7A real remittance batch posting design gate controls
    "run_real_remittance_batch_design_gate": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_real_remittance_batch_design_gate": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 6H real remittance PE smoke + rollback evidence freeze controls
    "run_real_remittance_pe_evidence_freeze": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_real_remittance_pe_evidence_freeze": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 6G controlled real remittance Payment Entry rollback controls
    "run_real_remittance_pe_smoke_rollback": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_real_remittance_pe_smoke_rollback_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 6F one controlled real remittance Payment Entry smoke controls
    "run_one_real_remittance_pe_smoke": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_one_real_remittance_pe_smoke_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 6E controlled eligible remittance source harness controls
    "run_real_remittance_pe_source_harness": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "cancel_real_remittance_pe_source_harness_audit": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 6D real remittance-to-PE activation gate controls
    "run_real_remittance_pe_activation_gate": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_real_remittance_pe_activation_gate": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 6C limited real remittance-to-PE hard-block adapter controls
    "run_real_remittance_pe_hard_block_adapter": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "cancel_real_remittance_pe_hard_block_adapter": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "create_real_remittance_payment_entries": [
        "System Manager",
        "NDIS CFO",
    ],

    # Phase 6B limited real remittance-to-PE preview controls
    "run_real_remittance_pe_preview": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "cancel_real_remittance_pe_preview": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 6A limited real remittance-to-PE design gate controls
    "run_real_remittance_pe_design_gate": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_real_remittance_pe_design_gate": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 5K Payment Entry live-smoke completion freeze controls
    "run_pe_live_smoke_completion_freeze": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_pe_live_smoke_completion_freeze": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 5J controlled rollback verification controls
    "run_pe_smoke_rollback_verification": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_pe_smoke_rollback_run": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 5I one submitted Payment Entry controlled smoke controls
    "run_pe_one_submitted_smoke": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_pe_one_submitted_smoke_payment": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_pe_one_submitted_smoke_run": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 5H controlled Sales Invoice source harness controls
    "run_pe_smoke_invoice_source_harness": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_pe_smoke_invoice_source": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_pe_smoke_invoice_source_run": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 5G submitted Payment Entry smoke gate controls
    "run_pe_submitted_smoke_gate": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_pe_submitted_smoke_gate": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "attempt_submitted_payment_entry_smoke": [
        "System Manager",
        "NDIS CFO",
    ],

    # Phase 5F single-record draft Payment Entry smoke controls
    "run_pe_single_record_draft_smoke": [
        "System Manager",
        "NDIS CFO",
    ],
    "cleanup_pe_single_record_draft_smoke": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_pe_single_record_draft_smoke": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "verify_pe_single_record_draft_submit_block": [
        "System Manager",
        "NDIS CFO",
    ],

    # Phase 5E production Payment Entry activation gate controls
    "run_pe_production_activation_gate": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_pe_production_activation_gate": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 5D production Payment Entry live adapter hard-block controls
    "run_pe_production_adapter_hard_block": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_pe_production_adapter_run": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "attempt_live_payment_entry_creation": [
        "System Manager",
        "NDIS CFO",
    ],

    # Phase 5C production Payment Entry posting preview controls
    "run_pe_production_posting_preview": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_pe_production_posting_preview": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 5B production Payment Entry account mapping hardening controls
    "run_pe_production_account_mapping_hardening": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_pe_production_account_mapping_gate": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 5A production Payment Entry posting design controls
    "manage_pe_production_posting_policy": [
        "System Manager",
        "NDIS CFO",
    ],
    "run_pe_production_design_gate": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_pe_production_design_gate": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 4D final Payment Entry sandbox readiness freeze controls
    "run_pe_sandbox_readiness_freeze": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_pe_sandbox_readiness_freeze": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Phase 4C sandbox accounting cleanup pack controls
    "run_sandbox_accounting_cleanup_pack": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_sandbox_accounting_cleanup_pack": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Invoice-backed sandbox Payment Entry smoke controls
    "run_invoice_backed_pe_smoke": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_invoice_backed_pe_smoke": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Sandbox Sales Invoice test-data harness controls
    "create_sandbox_invoice_test_data": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_sandbox_invoice_test_run": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Payment Entry sandbox completion gate controls
    "run_payment_entry_sandbox_completion_gate": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],
    "cancel_payment_entry_sandbox_completion_gate": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Sandbox Payment Entry cleanup controls
    "run_sandbox_payment_entry_cleanup": [
        "System Manager",
        "NDIS CFO",
    ],
    "cancel_sandbox_payment_entry_cleanup": [
        "System Manager",
        "NDIS CFO",
        "NDIS Finance Manager",
    ],

    # Sandbox-only Payment Entry adapter controls
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
