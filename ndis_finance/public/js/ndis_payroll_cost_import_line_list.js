frappe.listview_settings["NDIS Payroll Cost Import Line"] = {
    get_indicator(doc) {
        const status = doc.status;

        if (status === "Allocated") return [__("Allocated"), "green", "status,=,Allocated"];
        if (status === "Cost Pool Created") return [__("Cost Pool Created"), "blue", "status,=,Cost Pool Created"];
        if (status === "Mapped") return [__("Mapped"), "blue", "status,=,Mapped"];
        if (status === "Unmapped") return [__("Unmapped"), "orange", "status,=,Unmapped"];
        if (status === "Skipped") return [__("Skipped"), "gray", "status,=,Skipped"];
        if (status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        if (status === "Error") return [__("Error"), "red", "status,=,Error"];

        return [__(status || "Imported"), "blue", `status,=,${status || "Imported"}`];
    },
};
