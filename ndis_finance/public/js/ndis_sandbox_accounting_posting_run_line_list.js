frappe.listview_settings["NDIS Sandbox Accounting Posting Run Line"] = {
    get_indicator(doc) {
        if (doc.status === "Inserted In Draft JE") return [__("Inserted"), "green", "status,=,Inserted In Draft JE"];
        if (doc.status === "Blocker") return [__("Blocker"), "red", "status,=,Blocker"];
        if (doc.status === "Warning") return [__("Warning"), "orange", "status,=,Warning"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        if (doc.line_type === "Debit") return [__("Debit"), "blue", "line_type,=,Debit"];
        if (doc.line_type === "Credit") return [__("Credit"), "green", "line_type,=,Credit"];
        return [__(doc.status || "Prepared"), "blue", `status,=,${doc.status || "Prepared"}`];
    }
};
