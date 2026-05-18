frappe.listview_settings["NDIS Cost Allocation Entry"] = {
    get_indicator(doc) {
        const status = doc.status;

        if (status === "Active") return [__("Active"), "green", "status,=,Active"];
        if (status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];

        return [__(status || "Active"), "green", `status,=,${status || "Active"}`];
    },
};
