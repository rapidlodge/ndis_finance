frappe.ui.form.on("NDIS Guarded Limited Operation Execution Gate", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Gate Items"), () => {
            frappe.set_route("List", "NDIS Guarded Limited Operation Execution Gate Item", {
                gate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Gate Report"), () => {
            frappe.set_route("query-report", "NDIS Guarded Limited Operation Execution Gate Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Guarded Limited Operation Execution Gate Guardrail Report");
        }, __("Open"));

        if (frm.doc.preview) {
            frm.add_custom_button(__("Open Phase 10H Preview"), () => {
                frappe.set_route("Form", "NDIS Guarded Limited Operation Preview", frm.doc.preview);
            }, __("Evidence"));
        }

        if (frm.doc.pre_check) {
            frm.add_custom_button(__("Open Phase 10G Pre Check"), () => {
                frappe.set_route("Form", "NDIS Controlled Limited Operation Pre Check", frm.doc.pre_check);
            }, __("Evidence"));
        }

        if (frm.doc.target_policy_doctype && frm.doc.target_policy) {
            frm.add_custom_button(__("Open Target Policy"), () => {
                frappe.set_route("Form", frm.doc.target_policy_doctype, frm.doc.target_policy);
            }, __("Policy"));
        }

        if (frm.doc.execution_gate_allowed) {
            frm.dashboard.set_headline_alert(
                __("Execution gate allowed for Phase 10J smoke only. No execution has occurred in Phase 10I."),
                "green"
            );
        }
    }
});