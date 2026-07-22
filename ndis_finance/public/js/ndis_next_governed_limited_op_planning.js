frappe.ui.form.on("NDIS Next Governed Limited Op Planning", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Planning Items"), () => {
            frappe.set_route("List", "NDIS Next Governed Limited Op Planning Item", {
                planning: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Planning Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Planning Report");
        }, __("Open"));

        const is_phase14j = frm.doc.planning_payment_entry === "ACC-PAY-2026-00016";
        const is_phase13x = frm.doc.planning_payment_entry === "ACC-PAY-2026-00015";
        const phase_planning_report = is_phase14j
            ? "NDIS Next Governed Limited Op Planning Phase14J Report"
            : (is_phase13x ? "NDIS Next Governed Limited Op Planning Phase13X Report" : "NDIS Next Governed Limited Op Planning Phase13L Report");
        const phase_guardrail_report = is_phase14j
            ? "NDIS Next Governed Limited Op Planning Phase14J Guardrail Report"
            : (is_phase13x ? "NDIS Next Governed Limited Op Planning Phase13X Guardrail Report" : "NDIS Next Governed Limited Op Planning Phase13L Guardrail Report");
        const phase_label = is_phase14j ? "Phase 14J" : (is_phase13x ? "Phase 13X" : "Phase 13L");
        const monitor_label = is_phase14j ? "Phase 14I Runtime Monitor" : (is_phase13x ? "Phase 13W Runtime Monitor" : "Phase 13K Runtime Monitor");

        frm.add_custom_button(__(`Open ${phase_label} Planning Report`), () => {
            frappe.set_route("query-report", phase_planning_report);
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Planning Guardrail Report");
        }, __("Open"));

        frm.add_custom_button(__(`Open ${phase_label} Guardrail Report`), () => {
            frappe.set_route("query-report", phase_guardrail_report);
        }, __("Open"));

        if (frm.doc.monitor) {
            frm.add_custom_button(__(`Open ${monitor_label}`), () => {
                frappe.set_route("Form", "NDIS Next Governed Limited Op Runtime Monitor", frm.doc.monitor);
            }, __("Evidence"));
        }

        if (frm.doc.gated_payment_entry) {
            frm.add_custom_button(__("Open Gated Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.gated_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.previous_gated_payment_entry) {
            frm.add_custom_button(__("Open Previous Gated Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.previous_gated_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.planning_payment_entry || frm.doc.monitored_payment_entry) {
            frm.add_custom_button(__("Open Planned Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.planning_payment_entry || frm.doc.monitored_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.planning_approved) {
            frm.dashboard.set_headline_alert(
                __("Governed limited-operation planning approved. Design gate can proceed next."),
                "green"
            );
        }
    }
});
