frappe.ui.form.on("NDIS Governed Next Op Preview", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Preview Items"), () => {
            frappe.set_route("List", "NDIS Governed Next Op Preview Item", {
                preview: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Preview Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Next Op Preview Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Next Op Preview Guardrail Report");
        }, __("Open"));

        if (frm.doc.validation) {
            frm.add_custom_button(__("Open Phase 11G Validation"), () => {
                frappe.set_route("Form", "NDIS Governed Limited Op Candidate Validation", frm.doc.validation);
            }, __("Evidence"));
        }

        if (frm.doc.preview_approved) {
            frm.dashboard.set_headline_alert(
                __("Preview approved. Final execution gate can proceed."),
                "green"
            );
        }
    }
});
