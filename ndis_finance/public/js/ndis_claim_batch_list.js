frappe.listview_settings["NDIS Claim Batch"] = {
    get_indicator(doc) {
        const status = doc.status;

        if (status === "Paid") return [__("Paid"), "green", "status,=,Paid"];
        if (status === "Part Paid") return [__("Part Paid"), "orange", "status,=,Part Paid"];
        if (status === "Rejected") return [__("Rejected"), "red", "status,=,Rejected"];
        if (status === "Submitted") return [__("Submitted"), "blue", "status,=,Submitted"];
        if (status === "Closed") return [__("Closed"), "gray", "status,=,Closed"];

        return [__(status || "Draft"), "gray", `status,=,${status || "Draft"}`];
    },
};
