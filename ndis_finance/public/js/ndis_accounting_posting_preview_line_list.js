frappe.listview_settings["NDIS Accounting Posting Preview Line"] = {
    get_indicator(doc) {
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        if (doc.status === "Blocker") return [__("Blocker"), "red", "status,=,Blocker"];
        if (doc.status === "Warning") return [__("Warning"), "orange", "status,=,Warning"];
        if (doc.line_type === "Debit") return [__("Debit"), "blue", "line_type,=,Debit"];
        if (doc.line_type === "Credit") return [__("Credit"), "green", "line_type,=,Credit"];

        return [__(doc.status || "Preview"), "blue", `status,=,${doc.status || "Preview"}`];
    }
};
