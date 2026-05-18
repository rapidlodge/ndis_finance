frappe.listview_settings["NDIS Payroll Cost Import"] = {
    get_indicator(doc) {
        const status = doc.status;

        if (status === "Allocated") return [__("Allocated"), "green", "status,=,Allocated"];
        if (status === "Partially Allocated") return [__("Partially Allocated"), "orange", "status,=,Partially Allocated"];
        if (status === "Imported") return [__("Imported"), "blue", "status,=,Imported"];
        if (status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        if (status === "Failed") return [__("Failed"), "red", "status,=,Failed"];

        return [__(status || "Draft"), "orange", `status,=,${status || "Draft"}`];
    },
};
