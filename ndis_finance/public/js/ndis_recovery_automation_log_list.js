frappe.listview_settings["NDIS Recovery Automation Log"] = {
    get_indicator(doc) {
        const status = doc.status;

        if (status === "Completed") return [__("Completed"), "green", "status,=,Completed"];
        if (status === "Completed With Exceptions") {
            return [__("With Exceptions"), "orange", "status,=,Completed With Exceptions"];
        }
        if (status === "Failed") return [__("Failed"), "red", "status,=,Failed"];
        if (status === "Started") return [__("Started"), "blue", "status,=,Started"];

        return [__(status || "Started"), "gray", `status,=,${status || "Started"}`];
    },
};
