frappe.ui.form.on("NDIS Limited Batch Adapter Activation Gate", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Gate Items"), () => {
            frappe.set_route("List", "NDIS Limited Batch Adapter Activation Gate Item", {
                activation_gate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Gate Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Batch Adapter Activation Gate Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Batch Adapter Activation Gate Guardrail Report");
        }, __("Open"));

        if (frm.doc.hard_block) {
            frm.add_custom_button(__("Open Phase 9Y Hard Block"), () => {
                frappe.set_route("Form", "NDIS Limited Batch Posting Adapter Hard Block", frm.doc.hard_block);
            }, __("Evidence"));
        }

        if (frm.doc.adapter_preview) {
            frm.add_custom_button(__("Open Phase 9X Preview"), () => {
                frappe.set_route("Form", "NDIS Limited Batch Posting Adapter Preview", frm.doc.adapter_preview);
            }, __("Evidence"));
        }

        if (frm.doc.target_policy_doctype && frm.doc.target_policy) {
            frm.add_custom_button(__("Open Target Policy"), () => {
                frappe.set_route("Form", frm.doc.target_policy_doctype, frm.doc.target_policy);
            }, __("Policy"));
        }

        if (frm.doc.adapter_activation_allowed) {
            frm.dashboard.set_headline_alert(
                __("Activation gate allowed for next guarded adapter smoke only. No PE/GL created."),
                "green"
            );
        }
    }
});
