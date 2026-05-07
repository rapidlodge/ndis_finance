frappe.listview_settings["NDIS Claim Line"] = {
    get_indicator(doc) {
        const status = doc.claim_status;

        if (status === "Paid") return [__("Paid"), "green", "claim_status,=,Paid"];
        if (status === "Short Paid") return [__("Short Paid"), "orange", "claim_status,=,Short Paid"];
        if (status === "Rejected") return [__("Rejected"), "red", "claim_status,=,Rejected"];
        if (status === "Reclaim Required") {
            return [__("Reclaim Required"), "red", "claim_status,=,Reclaim Required"];
        }
        if (status === "Submitted") return [__("Submitted"), "blue", "claim_status,=,Submitted"];
        if (status === "Ready to Claim") {
            return [__("Ready to Claim"), "orange", "claim_status,=,Ready to Claim"];
        }
        if (status === "Invoice Cancelled") {
            return [__("Invoice Cancelled"), "gray", "claim_status,=,Invoice Cancelled"];
        }

        return [__(status || "Draft"), "gray", `claim_status,=,${status || "Draft"}`];
    },
};
