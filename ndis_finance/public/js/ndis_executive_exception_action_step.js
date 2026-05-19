frappe.ui.form.on("NDIS Executive Exception Action Step", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.action_plan) {
            frm.add_custom_button(__("Open Action Plan"), () => {
                frappe.set_route("Form", "NDIS Executive Exception Action Plan", frm.doc.action_plan);
            }, __("Open"));
        }

        if (frm.doc.status === "Open") {
            frm.add_custom_button(__("Mark In Progress"), () => {
                frappe.prompt([
                    {
                        fieldname: "note",
                        label: __("Follow-up Note"),
                        fieldtype: "Small Text"
                    }
                ], (values) => {
                    frappe.call({
                        method: "ndis_finance.services.executive_action_plans.mark_step_in_progress",
                        args: {
                            step: frm.doc.name,
                            note: values.note
                        },
                        freeze: true,
                        freeze_message: __("Updating step..."),
                        callback() {
                            frm.reload_doc();
                        }
                    });
                }, __("Mark In Progress"), __("Confirm"));
            }, __("NDIS Actions"));
        }

        if (!["Completed", "Cancelled"].includes(frm.doc.status)) {
            frm.add_custom_button(__("Complete Step"), () => {
                frappe.prompt([
                    {
                        fieldname: "completion_note",
                        label: __("Completion Note"),
                        fieldtype: "Small Text",
                        reqd: 1
                    },
                    {
                        fieldname: "evidence_attachment",
                        label: __("Evidence Attachment"),
                        fieldtype: "Attach"
                    }
                ], (values) => {
                    frappe.call({
                        method: "ndis_finance.services.executive_action_plans.complete_action_step",
                        args: {
                            step: frm.doc.name,
                            completion_note: values.completion_note,
                            evidence_attachment: values.evidence_attachment
                        },
                        freeze: true,
                        freeze_message: __("Completing step..."),
                        callback() {
                            frm.reload_doc();
                        }
                    });
                }, __("Complete Step"), __("Complete"));
            }, __("NDIS Actions"));
        }
    }
});
