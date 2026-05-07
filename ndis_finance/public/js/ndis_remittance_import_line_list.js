frappe.listview_settings["NDIS Remittance Import Line"] = {
    get_indicator(doc) {
        const status = doc.status;

        if (status === "Applied") return [__("Applied"), "green", "status,=,Applied"];
        if (status === "Matched") return [__("Matched"), "blue", "status,=,Matched"];
        if (status === "Multiple Matches") return [__("Multiple Matches"), "orange", "status,=,Multiple Matches"];
        if (status === "Unmatched") return [__("Unmatched"), "red", "status,=,Unmatched"];
        if (status === "Error") return [__("Error"), "red", "status,=,Error"];
        if (status === "Skipped") return [__("Skipped"), "gray", "status,=,Skipped"];

        return [__(status || "Imported"), "gray", `status,=,${status || "Imported"}`];
    }
};
