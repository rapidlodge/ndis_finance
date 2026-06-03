frappe.listview_settings["NDIS Controlled Production Batch Posting Policy"] = {
    get_indicator(doc) {
        if (doc.production_batch_enabled || doc.live_posting_allowed) return [__("Live Enabled"), "red", "production_batch_enabled,=,1"];
        if (doc.status === "Active") return [__("Design Only"), "green", "status,=,Active"];
        if (doc.status === "Inactive") return [__("Inactive"), "gray", "status,=,Inactive"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
