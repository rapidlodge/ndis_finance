frappe.listview_settings["NDIS Claim Export Mapping Template"] = {
    get_indicator(doc) {
        if (!doc.active) {
            return [__("Inactive"), "gray", "active,=,0"];
        }

        if (doc.is_default) {
            return [__("Default"), "green", "is_default,=,1"];
        }

        return [__("Active"), "blue", "active,=,1"];
    },
};
