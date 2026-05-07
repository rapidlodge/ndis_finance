frappe.listview_settings["NDIS Recovery Email Draft"] = {
    get_indicator(doc) {
        const status = doc.status;

        if (status === "Draft") return [__("Draft"), "orange", "status,=,Draft"];
        if (status === "Approved") return [__("Approved"), "blue", "status,=,Approved"];
        if (status === "Sent Manually") {
            return [__("Sent Manually"), "green", "status,=,Sent Manually"];
        }
        if (status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];

        return [__(status || "Draft"), "gray", `status,=,${status || "Draft"}`];
    },
};
