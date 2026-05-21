frappe.listview_settings["NDIS Payment Entry Allocation Preview Line"] = {
    get_indicator(doc) {
        if (doc.status === "Allocatable") return [__("Allocatable"), "green", "status,=,Allocatable"];
        if (doc.status === "Exception") return [__("Exception"), "orange", "status,=,Exception"];
        if (doc.status === "Duplicate") return [__("Duplicate"), "red", "status,=,Duplicate"];
        if (doc.status === "Excluded") return [__("Excluded"), "gray", "status,=,Excluded"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Exception"), "blue", `status,=,${doc.status || "Exception"}`];
    }
};
