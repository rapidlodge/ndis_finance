frappe.ui.form.on("NDIS Executive Exception Action Plan", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Steps"), () => {
            frappe.set_route("List", "NDIS Executive Exception Action Step", {
                action_plan: frm.doc.name
            });
        }, __("Open"));

        if (frm.doc.exception_alert) {
            frm.add_custom_button(__("Open Alert"), () => {
                frappe.set_route("Form", "NDIS Executive Exception Alert", frm.doc.exception_alert);
            }, __("Open"));
        }

        if (frm.doc.exception_rule) {
            frm.add_custom_button(__("Open Rule"), () => {
                frappe.set_route("Form", "NDIS Executive Exception Rule", frm.doc.exception_rule);
            }, __("Open"));
        }

        frm.add_custom_button(__("Add Action Step"), () => {
            frappe.prompt([
                { fieldname: "action_title", label: __("Action Title"), fieldtype: "Data", reqd: 1 },
                { fieldname: "action_detail", label: __("Action Detail"), fieldtype: "Small Text" },
                { fieldname: "assigned_to", label: __("Assigned To"), fieldtype: "Link", options: "User" },
                { fieldname: "due_date", label: __("Due Date"), fieldtype: "Date" }
            ], (values) => {
                frappe.call({
                    method: "ndis_finance.services.executive_action_plans.add_action_step",
                    args: {
                        action_plan: frm.doc.name,
                        action_title: values.action_title,
                        action_detail: values.action_detail,
                        assigned_to: values.assigned_to,
                        due_date: values.due_date
                    },
                    freeze: true,
                    freeze_message: __("Adding action step..."),
                    callback() {
                        frm.reload_doc();
                    }
                });
            }, __("Add Action Step"), __("Add"));
        }, __("NDIS Actions"));

        frm.add_custom_button(__("Refresh Summary"), () => {
            frappe.call({
                method: "ndis_finance.services.executive_action_plans.refresh_action_plan_summary",
                args: { action_plan: frm.doc.name },
                freeze: true,
                freeze_message: __("Refreshing action plan summary..."),
                callback() {
                    frm.reload_doc();
                }
            });
        }, __("NDIS Actions"));

        if (!["Completed", "Cancelled"].includes(frm.doc.status)) {
            frm.add_custom_button(__("Escalate"), () => {
                frappe.prompt([
                    {
                        fieldname: "escalation_level",
                        label: __("Escalation Level"),
                        fieldtype: "Select",
                        options: "\nLevel 1\nLevel 2\nLevel 3\nExecutive",
                        reqd: 1
                    },
                    {
                        fieldname: "escalation_note",
                        label: __("Escalation Note"),
                        fieldtype: "Small Text",
                        reqd: 1
                    }
                ], (values) => {
                    frappe.call({
                        method: "ndis_finance.services.executive_action_plans.escalate_action_plan",
                        args: {
                            action_plan: frm.doc.name,
                            escalation_level: values.escalation_level,
                            escalation_note: values.escalation_note
                        },
                        freeze: true,
                        freeze_message: __("Escalating action plan..."),
                        callback() {
                            frm.reload_doc();
                        }
                    });
                }, __("Escalate Action Plan"), __("Escalate"));
            }, __("NDIS Actions"));

            frm.add_custom_button(__("Complete Action Plan"), () => {
                frappe.prompt([
                    {
                        fieldname: "resolution_summary",
                        label: __("Resolution Summary"),
                        fieldtype: "Small Text",
                        reqd: 1
                    },
                    {
                        fieldname: "resolution_evidence",
                        label: __("Resolution Evidence"),
                        fieldtype: "Attach"
                    },
                    {
                        fieldname: "management_sign_off",
                        label: __("Management Sign-off"),
                        fieldtype: "Check",
                        default: 1
                    }
                ], (values) => {
                    frappe.call({
                        method: "ndis_finance.services.executive_action_plans.complete_action_plan",
                        args: {
                            action_plan: frm.doc.name,
                            resolution_summary: values.resolution_summary,
                            resolution_evidence: values.resolution_evidence,
                            management_sign_off: values.management_sign_off
                        },
                        freeze: true,
                        freeze_message: __("Completing action plan..."),
                        callback() {
                            frm.reload_doc();
                            frappe.show_alert({
                                message: __("Action plan completed internally only."),
                                indicator: "green"
                            });
                        }
                    });
                }, __("Complete Action Plan"), __("Complete"));
            }, __("NDIS Actions"));

            frm.add_custom_button(__("Cancel Action Plan"), () => {
                frappe.prompt([
                    {
                        fieldname: "reason",
                        label: __("Cancellation Reason"),
                        fieldtype: "Small Text",
                        reqd: 1
                    }
                ], (values) => {
                    frappe.call({
                        method: "ndis_finance.services.executive_action_plans.cancel_action_plan",
                        args: {
                            action_plan: frm.doc.name,
                            reason: values.reason
                        },
                        freeze: true,
                        freeze_message: __("Cancelling action plan..."),
                        callback() {
                            frm.reload_doc();
                        }
                    });
                }, __("Cancel Action Plan"), __("Cancel"));
            }, __("NDIS Actions"));
        }
    }
});
