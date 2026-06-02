frappe.ui.form.on("NDIS Real Remittance Batch Source Harness Run", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Source Lines"), () => {
            frappe.set_route("List", "NDIS Real Remittance Batch Source Harness Line", {
                source_run: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Harness Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance Batch Source Harness Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Line Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance Batch Source Harness Line Report", {
                source_run: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrails"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance Batch Source Harness Guardrail Report");
        }, __("Open"));

        if (frm.doc.activation_gate) {
            frm.add_custom_button(__("Open Phase 7D Gate"), () => {
                frappe.set_route("Form", "NDIS Real Remittance Batch Activation Gate", frm.doc.activation_gate);
            }, __("Evidence"));
        }

        if (frm.doc.source_remittance_import) {
            frm.add_custom_button(__("Open Remittance Import"), () => {
                frappe.set_route("Form", "NDIS Remittance Import", frm.doc.source_remittance_import);
            }, __("Evidence"));
        }
    }
});
