frappe.listview_settings["NDIS Accounting Posting Request"] = {
    get_indicator(doc) {
        if (doc.status === "Dry Run Passed") return [__("Dry Run Passed"), "green", "status,=,Dry Run Passed"];
        if (doc.status === "Approved") return [__("Approved"), "green", "status,=,Approved"];
        if (doc.status === "Pending Approval") return [__("Pending Approval"), "orange", "status,=,Pending Approval"];
        if (["Blocked", "Dry Run Failed"].includes(doc.status)) return [__(doc.status), "red", `status,=,${doc.status}`];
        if (["Cancelled", "Rejected"].includes(doc.status)) return [__(doc.status), "gray", `status,=,${doc.status}`];

        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
