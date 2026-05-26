frappe.listview_settings["NDIS PE Production Posting Preview Line"] = {
    get_indicator(doc) {
        if (doc.status === "Preview Eligible") return [__("Preview Eligible"), "green", "status,=,Preview Eligible"];
        if (doc.status === "Blocked") return [__("Blocked"), "orange", "status,=,Blocked"];
        if (doc.status === "Duplicate") return [__("Duplicate"), "orange", "status,=,Duplicate"];
        if (doc.status === "Warning") return [__("Warning"), "orange", "status,=,Warning"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Info"), "blue", `status,=,${doc.status || "Info"}`];
    }
};
