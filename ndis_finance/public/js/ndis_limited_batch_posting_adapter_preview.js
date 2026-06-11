frappe.ui.form.on("NDIS Limited Batch Posting Adapter Preview", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Preview Items"), () => {
            frappe.set_route("List", "NDIS Limited Batch Posting Adapter Preview Item", {
                adapter_preview: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Preview Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Batch Posting Adapter Preview Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Batch Posting Adapter Preview Guardrail Report");
        }, __("Open"));

        if (frm.doc.runtime_guard_evidence_freeze) {
            frm.add_custom_button(__("Open Phase 9W Freeze"), () => {
                frappe.set_route("Form", "NDIS Limited Batch Runtime Guard Evidence Freeze", frm.doc.runtime_guard_evidence_freeze);
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

        if (frm.doc.adapter_preview_approved) {
            frm.dashboard.set_headline_alert(
                __("Guarded posting adapter preview approved. No Payment Entry or GL has been created."),
                "green"
            );
        }
    }
});
