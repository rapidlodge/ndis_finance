frappe.listview_settings["NDIS Accounting Posting Preview"] = {
    get_indicator(doc) {
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        if (doc.validation_status === "Blocked") return [__("Blocked"), "red", "validation_status,=,Blocked"];
        if (doc.validation_status === "Warning") return [__("Warning"), "orange", "validation_status,=,Warning"];
        if (doc.validation_status === "Pass") return [__("Pass"), "green", "validation_status,=,Pass"];

        return [__(doc.status || "Previewed"), "blue", `status,=,${doc.status || "Previewed"}`];
    }
};
