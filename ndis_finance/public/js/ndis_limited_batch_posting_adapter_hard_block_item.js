frappe.ui.form.on("NDIS Limited Batch Posting Adapter Hard Block Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.hard_block) {
            frm.add_custom_button(__("Open Hard Block"), () => {
                frappe.set_route("Form", "NDIS Limited Batch Posting Adapter Hard Block", frm.doc.hard_block);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Source"));
        }
    }
});
