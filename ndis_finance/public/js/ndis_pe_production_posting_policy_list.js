frappe.listview_settings["NDIS PE Production Posting Policy"] = {
    get_indicator(doc) {
        if (doc.production_posting_enabled) return [__("Live Enabled"), "red", "production_posting_enabled,=,1"];
        if (doc.policy_status === "Design Approved") return [__("Design Approved"), "green", "policy_status,=,Design Approved"];
        if (doc.policy_status === "Needs Review") return [__("Needs Review"), "orange", "policy_status,=,Needs Review"];
        if (doc.policy_status === "Blocked") return [__("Blocked"), "red", "policy_status,=,Blocked"];
        if (doc.policy_status === "Inactive") return [__("Inactive"), "gray", "policy_status,=,Inactive"];
        return [__(doc.policy_status || "Draft"), "blue", `policy_status,=,${doc.policy_status || "Draft"}`];
    }
};
