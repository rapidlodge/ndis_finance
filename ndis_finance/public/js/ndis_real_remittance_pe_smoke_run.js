frappe.ui.form.on("NDIS Real Remittance PE Smoke Run", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Smoke Lines"), () => {
            frappe.set_route("List", "NDIS Real Remittance PE Smoke Line", { smoke_run: frm.doc.name });
        }, __("Open"));

        frm.add_custom_button(__("Open Smoke Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance PE Smoke Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance PE Smoke Guardrail Report");
        }, __("Open"));

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Result"));
        }

        if (frm.doc.sales_invoice) {
            frm.add_custom_button(__("Open Sales Invoice"), () => {
                frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
            }, __("Source"));
        }

        if (frm.doc.activation_gate) {
            frm.add_custom_button(__("Open Phase 6D Gate"), () => {
                frappe.set_route("Form", "NDIS Real Remittance PE Activation Gate", frm.doc.activation_gate);
            }, __("Evidence"));
        }

        if (frm.doc.source_harness_run) {
            frm.add_custom_button(__("Open Phase 6E Harness"), () => {
                frappe.set_route("Form", "NDIS Real Remittance PE Source Harness Run", frm.doc.source_harness_run);
            }, __("Evidence"));
        }
    }
});
