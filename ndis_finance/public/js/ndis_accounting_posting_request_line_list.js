frappe.listview_settings["NDIS Accounting Posting Request Line"] = {
    get_indicator(doc) {
        if (doc.status === "Simulated") return [__("Simulated"), "green", "status,=,Simulated"];
        if (doc.status === "Blocker") return [__("Blocker"), "red", "status,=,Blocker"];
        if (doc.status === "Warning") return [__("Warning"), "orange", "status,=,Warning"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        if (doc.line_type === "Debit") return [__("Debit"), "blue", "line_type,=,Debit"];
        if (doc.line_type === "Credit") return [__("Credit"), "green", "line_type,=,Credit"];

        return [__(doc.status || "Ready"), "blue", `status,=,${doc.status || "Ready"}`];
    }
};
