frappe.listview_settings["NDIS Remittance Import"] = {
    get_indicator(doc) {
        const status = doc.status;

        if (status === "Applied") return [__("Applied"), "green", "status,=,Applied"];
        if (status === "Partially Applied") return [__("Partially Applied"), "orange", "status,=,Partially Applied"];
        if (status === "Matched") return [__("Matched"), "blue", "status,=,Matched"];
        if (status === "Partially Matched") return [__("Partially Matched"), "orange", "status,=,Partially Matched"];
        if (status === "Failed") return [__("Failed"), "red", "status,=,Failed"];
        if (status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];

        return [__(status || "Draft"), "gray", `status,=,${status || "Draft"}`];
    }
};
