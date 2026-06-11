frappe.ui.form.on("NDIS Limited Batch Posting Adapter Hard Block", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Hard Block Items"), () => {
            frappe.set_route("List", "NDIS Limited Batch Posting Adapter Hard Block Item", {
                hard_block: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Hard Block Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Batch Posting Adapter Hard Block Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Batch Posting Adapter Hard Block Guardrail Report");
        }, __("Open"));

        if (frm.doc.adapter_preview) {
            frm.add_custom_button(__("Open Phase 9X Preview"), () => {
                frappe.set_route("Form", "NDIS Limited Batch Posting Adapter Preview", frm.doc.adapter_preview);
            }, __("Evidence"));
        }

        if (frm.doc.runtime_guard) {
            frm.add_custom_button(__("Open Phase 9V Guard"), () => {
                frappe.set_route("Form", "NDIS Limited Batch Runtime Guard", frm.doc.runtime_guard);
            }, __("Evidence"));
        }

        if (frm.doc.target_policy_doctype && frm.doc.target_policy) {
            frm.add_custom_button(__("Open Target Policy"), () => {
                frappe.set_route("Form", frm.doc.target_policy_doctype, frm.doc.target_policy);
            }, __("Policy"));
        }

        if (frm.doc.adapter_hard_blocked) {
            frm.dashboard.set_headline_alert(
                __("Adapter hard-block proof passed. Direct execution is blocked and no PE/GL was created."),
                "green"
            );
        }
    }
});
