frappe.listview_settings["NDIS Payment Reconciliation Batch"] = {
    get_indicator(doc) {
        const status = doc.status;

        if (status === "Reconciled") return [__("Reconciled"), "green", "status,=,Reconciled"];
        if (status === "Exception") return [__("Exception"), "red", "status,=,Exception"];
        if (status === "Partially Reconciled") {
            return [__("Partially Reconciled"), "orange", "status,=,Partially Reconciled"];
        }
        if (status === "Closed") return [__("Closed"), "gray", "status,=,Closed"];

        return [__(status || "Draft"), "gray", `status,=,${status || "Draft"}`];
    },
};
