frappe.listview_settings["NDIS Real Remittance PE Adapter Run Line"] = {
    get_indicator(doc) {
        if (doc.adapter_status === "Hard Blocked") return [__("Hard Blocked"), "green", "adapter_status,=,Hard Blocked"];
        if (doc.adapter_status === "Validation Blocked") return [__("Validation Blocked"), "red", "adapter_status,=,Validation Blocked"];
        if (doc.adapter_status === "Review Blocked") return [__("Review Blocked"), "orange", "adapter_status,=,Review Blocked"];
        if (doc.adapter_status === "Cancelled") return [__("Cancelled"), "gray", "adapter_status,=,Cancelled"];
        return [__(doc.adapter_status || "Source Pending"), "orange", `adapter_status,=,${doc.adapter_status || "Source Pending"}`];
    }
};
