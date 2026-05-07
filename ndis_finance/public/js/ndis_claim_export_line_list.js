frappe.listview_settings["NDIS Claim Export Line"] = {
    get_indicator(doc) {
        const status = doc.export_status;

        if (status === "Exported") return [__("Exported"), "green", "export_status,=,Exported"];
        if (status === "Skipped") return [__("Skipped"), "orange", "export_status,=,Skipped"];
        if (status === "Cancelled") return [__("Cancelled"), "gray", "export_status,=,Cancelled"];

        return [__(status || "Exported"), "gray", `export_status,=,${status || "Exported"}`];
    },
};
