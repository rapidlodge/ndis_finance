frappe.listview_settings["NDIS Funding Leakage Register"] = {
    get_indicator(doc) {
        const status = doc.status;

        if (status === "Open") return [__("Open"), "red", "status,=,Open"];
        if (status === "In Review") return [__("In Review"), "orange", "status,=,In Review"];
        if (status === "Resolved") return [__("Resolved"), "green", "status,=,Resolved"];
        if (status === "Written Off") return [__("Written Off"), "gray", "status,=,Written Off"];
        if (status === "Closed") return [__("Closed"), "gray", "status,=,Closed"];

        return [__(status || "Open"), "gray", `status,=,${status || "Open"}`];
    },
};
