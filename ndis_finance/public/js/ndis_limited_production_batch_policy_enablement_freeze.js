frappe.ui.form.on("NDIS Limited Production Batch Policy Enablement Freeze", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Freeze Lines"), () => {
            frappe.set_route("List", "NDIS Limited Production Batch Policy Enablement Freeze Line", {
                evidence_freeze: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Freeze Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Policy Enablement Freeze Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Policy Enablement Freeze Guardrail Report");
        }, __("Open"));

        if (frm.doc.enablement_run) {
            frm.add_custom_button(__("Open Phase 9S Enablement"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Policy Enablement Run", frm.doc.enablement_run);
            }, __("Evidence"));
        }

        if (frm.doc.readiness_gate) {
            frm.add_custom_button(__("Open Phase 9R Readiness"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Enablement Readiness Gate", frm.doc.readiness_gate);
            }, __("Evidence"));
        }

        if (frm.doc.target_policy_doctype && frm.doc.target_policy) {
            frm.add_custom_button(__("Open Target Policy"), () => {
                frappe.set_route("Form", frm.doc.target_policy_doctype, frm.doc.target_policy);
            }, __("Policy"));
        }

        if (frm.doc.ready_for_limited_batch_monitoring) {
            frm.dashboard.set_headline_alert(
                __("Controlled limited production policy enablement evidence frozen. Live posting remains blocked."),
                "green"
            );
        }
    }
});
