frappe.ui.form.on("NDIS PE Live Smoke Completion Freeze", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Freeze Items"), () => {
            frappe.set_route("List", "NDIS PE Live Smoke Completion Freeze Item", {
                completion_freeze: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Freeze Report"), () => {
            frappe.set_route("query-report", "NDIS PE Live Smoke Completion Freeze Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Exception Report"), () => {
            frappe.set_route("query-report", "NDIS PE Live Smoke Completion Exception Report", {
                completion_freeze: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open GL Evidence"), () => {
            frappe.set_route("query-report", "NDIS PE Live Smoke Completion GL Evidence Report");
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

        if (frm.doc.phase5j_rollback_run) {
            frm.add_custom_button(__("Open Phase 5J Rollback"), () => {
                frappe.set_route("Form", "NDIS PE Smoke Rollback Run", frm.doc.phase5j_rollback_run);
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
