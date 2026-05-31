frappe.ui.form.on("NDIS PE Smoke Rollback Run", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Run Items"), () => {
            frappe.set_route("List", "NDIS PE Smoke Rollback Run Item", {
                rollback_run: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Run Report"), () => {
            frappe.set_route("query-report", "NDIS PE Smoke Rollback Run Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Exception Report"), () => {
            frappe.set_route("query-report", "NDIS PE Smoke Rollback Exception Report", {
                rollback_run: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open GL Report"), () => {
            frappe.set_route("query-report", "NDIS PE Smoke Rollback GL Report");
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

        if (frm.doc.phase5i_run) {
            frm.add_custom_button(__("Open Phase 5I Run"), () => {
                frappe.set_route("Form", "NDIS PE One Submitted Smoke Run", frm.doc.phase5i_run);
            }, __("Evidence"));
        }

        if (frm.doc.phase5h_source_run) {
            frm.add_custom_button(__("Open Phase 5H Source Run"), () => {
                frappe.set_route("Form", "NDIS PE Smoke Invoice Source Run", frm.doc.phase5h_source_run);
            }, __("Evidence"));
        }
    }
});
