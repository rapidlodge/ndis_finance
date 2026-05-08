frappe.ui.form.on("NDIS Claim Export Mapping Template", {
    refresh(frm) {
        if (frm.is_new()) {
            return;
        }

        frm.add_custom_button(__("Preview Template Columns"), () => {
            frappe.call({
                method: "ndis_finance.services.claim_exporter.preview_export_template",
                args: {
                    export_mapping_template: frm.doc.name,
                    export_type: frm.doc.export_type,
                },
                freeze: true,
                freeze_message: __("Previewing export template..."),
                callback(r) {
                    const msg = r.message || {};
                    frappe.msgprint({
                        title: __("Export Template Preview"),
                        message: `<pre>${JSON.stringify(msg, null, 2)}</pre>`,
                        indicator: "blue",
                    });
                },
            });
        }, __("NDIS Actions"));
    },
});
