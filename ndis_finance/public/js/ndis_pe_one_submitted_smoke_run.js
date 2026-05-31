frappe.ui.form.on("NDIS PE One Submitted Smoke Run", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Run Items"), () => {
            frappe.set_route("List", "NDIS PE One Submitted Smoke Run Item", {
                submitted_run: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Run Report"), () => {
            frappe.set_route("query-report", "NDIS PE One Submitted Smoke Run Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Exception Report"), () => {
            frappe.set_route("query-report", "NDIS PE One Submitted Smoke Exception Report", {
                submitted_run: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open PE GL Report"), () => {
            frappe.set_route("query-report", "NDIS PE One Submitted Smoke GL Report", {
                payment_entry: frm.doc.payment_entry
            });
        }, __("Open"));

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Evidence"));
        }

        if (frm.doc.source_sales_invoice) {
            frm.add_custom_button(__("Open Source Sales Invoice"), () => {
                frappe.set_route("Form", "Sales Invoice", frm.doc.source_sales_invoice);
            }, __("Evidence"));
        }

        if (frm.doc.source_invoice_run) {
            frm.add_custom_button(__("Open Phase 5H Source Run"), () => {
                frappe.set_route("Form", "NDIS PE Smoke Invoice Source Run", frm.doc.source_invoice_run);
            }, __("Evidence"));
        }
    }
});
