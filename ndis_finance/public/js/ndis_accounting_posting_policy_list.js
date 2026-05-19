frappe.listview_settings["NDIS Accounting Posting Policy"] = {
    get_indicator(doc) {
        if (doc.policy_status === "Suspended") return [__("Suspended"), "orange", "policy_status,=,Suspended"];
        if (doc.policy_status === "Retired") return [__("Retired"), "gray", "policy_status,=,Retired"];
        if (doc.posting_mode === "Management Only") return [__("Management Only"), "green", "posting_mode,=,Management Only"];
        if (doc.posting_mode === "Preview Only") return [__("Preview Only"), "blue", "posting_mode,=,Preview Only"];
        if (doc.posting_mode === "Future Controlled Posting") return [__("Future Controlled"), "orange", "posting_mode,=,Future Controlled Posting"];
        if (doc.posting_mode === "Disabled") return [__("Disabled"), "red", "posting_mode,=,Disabled"];

        return [__(doc.policy_status || "Active"), "blue", `policy_status,=,${doc.policy_status || "Active"}`];
    }
};
