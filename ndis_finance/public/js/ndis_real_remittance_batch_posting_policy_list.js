frappe.listview_settings["NDIS Real Remittance Batch Posting Policy"] = {
    get_indicator(doc) {
        if (doc.batch_live_enabled) return [__("Live Enabled"), "red", "batch_live_enabled,=,1"];
        if (doc.policy_status === "Active") return [__("Active"), "green", "policy_status,=,Active"];
        if (doc.policy_status === "Retired") return [__("Retired"), "gray", "policy_status,=,Retired"];
        return [__(doc.policy_status || "Draft"), "blue", `policy_status,=,${doc.policy_status || "Draft"}`];
    }
};
