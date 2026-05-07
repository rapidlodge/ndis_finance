frappe.listview_settings["NDIS Claim Export"] = {
    get_indicator(doc) {
        const status = doc.status;

        if (status === "Generated") return [__("Generated"), "green", "status,=,Generated"];
        if (status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];

        return [__(status || "Draft"), "orange", `status,=,${status || "Draft"}`];
    },
};
