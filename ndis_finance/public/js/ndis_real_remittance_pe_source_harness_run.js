frappe.ui.form.on("NDIS Real Remittance PE Source Harness Run", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Harness Lines"), () => {
            frappe.set_route("List", "NDIS Real Remittance PE Source Harness Line", {
                harness_run: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Harness Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance PE Source Harness Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Readiness Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance PE Source Harness Readiness Report");
        }, __("Open"));

        if (frm.doc.sales_invoice) {
            frm.add_custom_button(__("Open Sales Invoice"), () => {
                frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
            }, __("Source"));
        }

        if (frm.doc.claim_line) {
            frm.add_custom_button(__("Open Claim Line"), () => {
                frappe.set_route("Form", "NDIS Claim Line", frm.doc.claim_line);
            }, __("Source"));
        }

        if (frm.doc.remittance_import) {
            frm.add_custom_button(__("Open Remittance Import"), () => {
                frappe.set_route("Form", "NDIS Remittance Import", frm.doc.remittance_import);
            }, __("Source"));
        }

        if (frm.doc.remittance_line) {
            frm.add_custom_button(__("Open Remittance Line"), () => {
                frappe.set_route("Form", "NDIS Remittance Import Line", frm.doc.remittance_line);
            }, __("Source"));
        }
    }
});
