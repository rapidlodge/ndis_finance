frappe.ui.form.on("NDIS Limited Operation Closeout Gate", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Closeout Items"), () => {
            frappe.set_route("List", "NDIS Limited Operation Closeout Gate Item", {
                closeout: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Closeout Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Operation Closeout Gate Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Operation Closeout Gate Guardrail Report");
        }, __("Open"));

        if (frm.doc.freeze) {
            frm.add_custom_button(__("Open Phase 10L Freeze"), () => {
                frappe.set_route("Form", "NDIS Single Guarded Op Smoke Rollback Freeze", frm.doc.freeze);
            }, __("Evidence"));
        }

        if (frm.doc.rollback) {
            frm.add_custom_button(__("Open Phase 10K Rollback"), () => {
                frappe.set_route("Form", "NDIS Single Guarded Limited Operation Smoke Rollback", frm.doc.rollback);
            }, __("Evidence"));
        }

        if (frm.doc.smoke) {
            frm.add_custom_button(__("Open Phase 10J Smoke"), () => {
                frappe.set_route("Form", "NDIS Single Guarded Limited Operation Smoke", frm.doc.smoke);
            }, __("Evidence"));
        }

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.closeout_approved) {
            frm.dashboard.set_headline_alert(
                __("Closeout approved. Controlled limited operations steady-state is ready."),
                "green"
            );
        }
    }
});
