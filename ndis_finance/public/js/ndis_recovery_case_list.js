frappe.listview_settings["NDIS Recovery Case"] = {
    get_indicator(doc) {
        const status = doc.status;

        if (status === "Open") return [__("Open"), "red", "status,=,Open"];
        if (status === "In Follow Up") {
            return [__("In Follow Up"), "orange", "status,=,In Follow Up"];
        }
        if (status === "Waiting For Response") {
            return [__("Waiting"), "blue", "status,=,Waiting For Response"];
        }
        if (status === "Escalated") return [__("Escalated"), "red", "status,=,Escalated"];
        if (status === "Resolved") return [__("Resolved"), "green", "status,=,Resolved"];
        if (status === "Written Off") return [__("Written Off"), "gray", "status,=,Written Off"];
        if (status === "Closed") return [__("Closed"), "gray", "status,=,Closed"];

        return [__(status || "Open"), "gray", `status,=,${status || "Open"}`];
    },
};
