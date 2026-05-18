import frappe
from frappe import _
from frappe.utils import flt, today


def currency():
    return frappe.defaults.get_global_default("currency") or "AUD"


def get_filter(filters, key, default=None):
    if not filters:
        return default
    return filters.get(key) or default


def build_where(conditions):
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)


def add_import_filters(filters, alias="pci"):
    conditions = []
    params = {}
    prefix = f"{alias}." if alias else ""

    filter_map = {
        "company": "company",
        "au_payroll_run_log": "au_payroll_run_log",
        "status": "status",
    }

    from_date = get_filter(filters, "from_date")
    to_date = get_filter(filters, "to_date")
    payroll_cost_import = get_filter(filters, "payroll_cost_import")

    if from_date:
        conditions.append(f"{prefix}period_end >= %(from_date)s")
        params["from_date"] = from_date
    if to_date:
        conditions.append(f"{prefix}period_start <= %(to_date)s")
        params["to_date"] = to_date
    if payroll_cost_import:
        conditions.append(f"{prefix}name = %(payroll_cost_import)s")
        params["payroll_cost_import"] = payroll_cost_import

    for key, fieldname in filter_map.items():
        value = get_filter(filters, key)
        if value:
            conditions.append(f"{prefix}{fieldname} = %({key})s")
            params[key] = value

    return conditions, params


def add_line_filters(filters, alias="pcl"):
    conditions = []
    params = {}
    prefix = f"{alias}." if alias else ""

    filter_map = {
        "payroll_cost_import": "payroll_cost_import",
        "au_payroll_run_log": "au_payroll_run_log",
        "employee": "employee",
        "house": "house",
    }

    line_status = get_filter(filters, "line_status")
    if line_status:
        conditions.append(f"{prefix}status = %(line_status)s")
        params["line_status"] = line_status

    for key, fieldname in filter_map.items():
        value = get_filter(filters, key)
        if value:
            conditions.append(f"{prefix}{fieldname} = %({key})s")
            params[key] = value

    return conditions, params


def add_allocation_filters(filters, alias="cae", cost_pool_alias="cp"):
    conditions = [f"{alias}.status = 'Active'", f"{alias}.cost_type = 'Payroll'"]
    params = {}

    from_date = get_filter(filters, "from_date")
    to_date = get_filter(filters, "to_date")
    if from_date:
        conditions.append(f"{alias}.period_end >= %(from_date)s")
        params["from_date"] = from_date
    if to_date:
        conditions.append(f"{alias}.period_start <= %(to_date)s")
        params["to_date"] = to_date

    for key in ["company", "house", "participant"]:
        value = get_filter(filters, key)
        if value:
            conditions.append(f"{alias}.{key} = %({key})s")
            params[key] = value

    for key in ["au_payroll_run_log", "payroll_cost_import"]:
        value = get_filter(filters, key)
        if value:
            conditions.append(f"{cost_pool_alias}.{key} = %({key})s")
            params[key] = value

    return conditions, params


def execute_payroll_cost_import_reconciliation_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions, params = add_import_filters(filters, "pci")
    params["currency"] = currency()

    columns = [
        col("payroll_cost_import", "Payroll Cost Import", "Link", "NDIS Payroll Cost Import", 210),
        col("import_id", "Import ID", "Data", width=260),
        col("status", "Status", "Data", width=120),
        col("au_payroll_run_log", "AU Payroll Run Log", "Link", "AU Payroll Run Log", 190),
        col("company", "Company", "Link", "Company", 160),
        col("period_start", "Period Start", "Date", width=120),
        col("period_end", "Period End", "Date", width=120),
        col("cost_basis", "Cost Basis", "Data", width=170),
        col("allocation_method", "Allocation Method", "Data", width=180),
        col("line_count", "Lines", "Int", width=80),
        col("mapped_line_count", "Mapped", "Int", width=90),
        col("unmapped_line_count", "Unmapped", "Int", width=100),
        col("cost_pool_count", "Cost Pools", "Int", width=100),
        col("allocated_cost_pool_count", "Allocated Pools", "Int", width=120),
        money_col("total_gross_amount", "Gross", 130),
        money_col("total_employer_super_liability", "Employer Super", 150),
        money_col("total_estimated_net_pay", "Estimated Net Pay", 150),
        money_col("total_import_cost_amount", "Imported Payroll Cost", 170),
        money_col("active_allocated_cost", "Active Allocated Cost", 170),
        money_col("allocation_variance", "Allocation Variance", 160),
        currency_col(),
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            pci.name AS payroll_cost_import,
            pci.import_id,
            pci.status,
            pci.au_payroll_run_log,
            pci.company,
            pci.period_start,
            pci.period_end,
            pci.cost_basis,
            pci.allocation_method,
            pci.line_count,
            pci.mapped_line_count,
            pci.unmapped_line_count,
            pci.cost_pool_count,
            pci.allocated_cost_pool_count,
            pci.total_gross_amount,
            pci.total_employer_super_liability,
            pci.total_estimated_net_pay,
            pci.total_import_cost_amount,
            COALESCE(SUM(CASE WHEN cae.status = 'Active' THEN cae.allocated_cost_amount ELSE 0 END), 0) AS active_allocated_cost,
            pci.total_import_cost_amount - COALESCE(SUM(CASE WHEN cae.status = 'Active' THEN cae.allocated_cost_amount ELSE 0 END), 0) AS allocation_variance,
            %(currency)s AS currency
        FROM `tabNDIS Payroll Cost Import` pci
        LEFT JOIN `tabNDIS Cost Pool` cp ON cp.payroll_cost_import = pci.name
        LEFT JOIN `tabNDIS Cost Allocation Entry` cae ON cae.cost_pool = cp.name
        {build_where(conditions)}
        GROUP BY pci.name
        ORDER BY pci.modified DESC
        """,
        params,
        as_dict=True,
    )

    chart = bar_chart(
        data,
        "import_id",
        [
            ("Imported Cost", "total_import_cost_amount"),
            ("Allocated Cost", "active_allocated_cost"),
        ],
    )
    summary = [
        summary_item(len(data), "Imports", "Int", "Blue"),
        summary_item(sum(flt(row.total_import_cost_amount) for row in data), "Imported Payroll Cost", "Currency", "Blue"),
        summary_item(sum(flt(row.active_allocated_cost) for row in data), "Allocated Payroll Cost", "Currency", "Green"),
        summary_item(sum(flt(row.allocation_variance) for row in data), "Allocation Variance", "Currency", "Orange"),
        summary_item(sum(int(row.unmapped_line_count or 0) for row in data), "Unmapped Lines", "Int", "Red"),
    ]

    return columns, data, None, chart, summary


def execute_payroll_cost_by_house_report(filters=None):
    filters = frappe._dict(filters or {})
    import_conditions, import_params = add_line_filters(filters, "pcl")
    allocation_conditions, allocation_params = add_allocation_filters(filters, "cae", "cp")

    columns = [
        col("house", "House", "Link", "NDIS House", 220),
        col("import_line_count", "Import Lines", "Int", width=110),
        col("employee_count", "Employees", "Int", width=100),
        money_col("gross_amount", "Gross", 130),
        money_col("employer_super_liability", "Employer Super", 150),
        money_col("estimated_net_pay", "Estimated Net Pay", 150),
        money_col("import_cost_amount", "Imported Payroll Cost", 170),
        money_col("allocated_payroll_cost", "Allocated Payroll Cost", 170),
        col("allocation_entry_count", "Allocation Entries", "Int", width=140),
        money_col("allocation_variance", "Variance", 130),
        currency_col(),
    ]

    import_data = frappe.db.sql(
        f"""
        SELECT
            COALESCE(NULLIF(pcl.house, ''), 'Unassigned') AS house,
            COUNT(*) AS import_line_count,
            COUNT(DISTINCT pcl.employee) AS employee_count,
            COALESCE(SUM(pcl.gross_amount), 0) AS gross_amount,
            COALESCE(SUM(pcl.employer_super_liability), 0) AS employer_super_liability,
            COALESCE(SUM(pcl.estimated_net_pay), 0) AS estimated_net_pay,
            COALESCE(SUM(pcl.import_cost_amount), 0) AS import_cost_amount
        FROM `tabNDIS Payroll Cost Import Line` pcl
        {build_where(import_conditions)}
        GROUP BY COALESCE(NULLIF(pcl.house, ''), 'Unassigned')
        """,
        import_params,
        as_dict=True,
    )
    allocation_data = frappe.db.sql(
        f"""
        SELECT
            COALESCE(NULLIF(cae.house, ''), 'Unassigned') AS house,
            COUNT(*) AS allocation_entry_count,
            COALESCE(SUM(cae.allocated_cost_amount), 0) AS allocated_payroll_cost
        FROM `tabNDIS Cost Allocation Entry` cae
        INNER JOIN `tabNDIS Cost Pool` cp ON cp.name = cae.cost_pool
        {build_where(allocation_conditions)}
        GROUP BY COALESCE(NULLIF(cae.house, ''), 'Unassigned')
        """,
        allocation_params,
        as_dict=True,
    )

    data = merge_house_rows(import_data, allocation_data)
    chart = bar_chart(
        data,
        "house",
        [
            ("Imported Payroll Cost", "import_cost_amount"),
            ("Allocated Payroll Cost", "allocated_payroll_cost"),
        ],
    )
    summary = [
        summary_item(sum(flt(row.import_cost_amount) for row in data), "Imported Payroll Cost", "Currency", "Blue"),
        summary_item(sum(flt(row.allocated_payroll_cost) for row in data), "Allocated Payroll Cost", "Currency", "Green"),
        summary_item(sum(flt(row.allocation_variance) for row in data), "Variance", "Currency", "Orange"),
        summary_item(sum(int(row.employee_count or 0) for row in data), "Employee-House Count", "Int", "Blue"),
    ]

    return columns, data, None, chart, summary


def merge_house_rows(import_data, allocation_data):
    import_map = {row.house: row for row in import_data}
    allocation_map = {row.house: row for row in allocation_data}
    data = []

    for key in sorted(set(import_map).union(set(allocation_map))):
        imported = import_map.get(key) or frappe._dict()
        allocated = allocation_map.get(key) or frappe._dict()
        import_cost = flt(imported.get("import_cost_amount"))
        allocated_cost = flt(allocated.get("allocated_payroll_cost"))

        data.append(
            frappe._dict(
                {
                    "house": key,
                    "import_line_count": int(imported.get("import_line_count") or 0),
                    "employee_count": int(imported.get("employee_count") or 0),
                    "gross_amount": flt(imported.get("gross_amount")),
                    "employer_super_liability": flt(imported.get("employer_super_liability")),
                    "estimated_net_pay": flt(imported.get("estimated_net_pay")),
                    "import_cost_amount": import_cost,
                    "allocated_payroll_cost": allocated_cost,
                    "allocation_entry_count": int(allocated.get("allocation_entry_count") or 0),
                    "allocation_variance": import_cost - allocated_cost,
                    "currency": currency(),
                }
            )
        )

    return sorted(data, key=lambda row: flt(row.import_cost_amount), reverse=True)


def execute_payroll_cost_by_participant_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions, params = add_allocation_filters(filters, "cae", "cp")
    params["currency"] = currency()

    columns = [
        col("participant", "Participant", "Link", "Customer", 220),
        col("house", "House", "Link", "NDIS House", 180),
        col("allocation_entry_count", "Allocation Entries", "Int", width=140),
        money_col("gross_claim_amount", "Gross Claims", 140),
        money_col("paid_amount", "Paid Revenue", 140),
        money_col("allocated_payroll_cost", "Allocated Payroll Cost", 170),
        money_col("payroll_margin_amount", "Payroll Margin", 150),
        col("payroll_margin_percent", "Payroll Margin %", "Percent", width=140),
        currency_col(),
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            COALESCE(NULLIF(cae.participant, ''), 'Unassigned') AS participant,
            COALESCE(NULLIF(cae.house, ''), 'Unassigned') AS house,
            COUNT(*) AS allocation_entry_count,
            COALESCE(MAX(cae.gross_claim_amount), 0) AS gross_claim_amount,
            COALESCE(MAX(cae.paid_amount), 0) AS paid_amount,
            COALESCE(SUM(cae.allocated_cost_amount), 0) AS allocated_payroll_cost,
            COALESCE(MAX(cae.paid_amount), 0) - COALESCE(SUM(cae.allocated_cost_amount), 0) AS payroll_margin_amount,
            CASE
                WHEN COALESCE(MAX(cae.paid_amount), 0) > 0
                THEN ROUND(((COALESCE(MAX(cae.paid_amount), 0) - COALESCE(SUM(cae.allocated_cost_amount), 0)) / COALESCE(MAX(cae.paid_amount), 0)) * 100, 2)
                ELSE 0
            END AS payroll_margin_percent,
            %(currency)s AS currency
        FROM `tabNDIS Cost Allocation Entry` cae
        INNER JOIN `tabNDIS Cost Pool` cp ON cp.name = cae.cost_pool
        {build_where(conditions)}
        GROUP BY COALESCE(NULLIF(cae.participant, ''), 'Unassigned'), COALESCE(NULLIF(cae.house, ''), 'Unassigned')
        ORDER BY allocated_payroll_cost DESC
        """,
        params,
        as_dict=True,
    )
    chart = bar_chart(
        data,
        "participant",
        [
            ("Paid Revenue", "paid_amount"),
            ("Payroll Cost", "allocated_payroll_cost"),
        ],
    )
    summary = [
        summary_item(sum(flt(row.paid_amount) for row in data), "Paid Revenue", "Currency", "Green"),
        summary_item(sum(flt(row.allocated_payroll_cost) for row in data), "Payroll Cost", "Currency", "Orange"),
        summary_item(sum(flt(row.payroll_margin_amount) for row in data), "Payroll Margin", "Currency", "Green"),
    ]

    return columns, data, None, chart, summary


def execute_payroll_profitability_impact_report(filters=None):
    filters = frappe._dict(filters or {})
    conditions, params = add_general_allocation_filters(filters)
    params["currency"] = currency()

    columns = [
        col("house", "House", "Link", "NDIS House", 180),
        col("participant", "Participant", "Link", "Customer", 220),
        money_col("paid_revenue", "Paid Revenue", 140),
        money_col("payroll_cost", "Payroll Cost", 140),
        money_col("non_payroll_cost", "Non-Payroll Cost", 160),
        money_col("total_allocated_cost", "Total Allocated Cost", 170),
        money_col("margin_after_payroll", "Margin After Payroll", 170),
        money_col("margin_after_all_costs", "Margin After All Costs", 180),
        col("payroll_cost_ratio", "Payroll Cost Ratio %", "Percent", width=150),
        col("total_margin_percent", "Total Margin %", "Percent", width=130),
        currency_col(),
    ]
    data = frappe.db.sql(
        f"""
        SELECT
            COALESCE(NULLIF(cae.house, ''), 'Unassigned') AS house,
            COALESCE(NULLIF(cae.participant, ''), 'Unassigned') AS participant,
            COALESCE(MAX(cae.paid_amount), 0) AS paid_revenue,
            COALESCE(SUM(CASE WHEN cae.cost_type = 'Payroll' THEN cae.allocated_cost_amount ELSE 0 END), 0) AS payroll_cost,
            COALESCE(SUM(CASE WHEN cae.cost_type != 'Payroll' THEN cae.allocated_cost_amount ELSE 0 END), 0) AS non_payroll_cost,
            COALESCE(SUM(cae.allocated_cost_amount), 0) AS total_allocated_cost,
            COALESCE(MAX(cae.paid_amount), 0) - COALESCE(SUM(CASE WHEN cae.cost_type = 'Payroll' THEN cae.allocated_cost_amount ELSE 0 END), 0) AS margin_after_payroll,
            COALESCE(MAX(cae.paid_amount), 0) - COALESCE(SUM(cae.allocated_cost_amount), 0) AS margin_after_all_costs,
            CASE
                WHEN COALESCE(MAX(cae.paid_amount), 0) > 0
                THEN ROUND((COALESCE(SUM(CASE WHEN cae.cost_type = 'Payroll' THEN cae.allocated_cost_amount ELSE 0 END), 0) / COALESCE(MAX(cae.paid_amount), 0)) * 100, 2)
                ELSE 0
            END AS payroll_cost_ratio,
            CASE
                WHEN COALESCE(MAX(cae.paid_amount), 0) > 0
                THEN ROUND(((COALESCE(MAX(cae.paid_amount), 0) - COALESCE(SUM(cae.allocated_cost_amount), 0)) / COALESCE(MAX(cae.paid_amount), 0)) * 100, 2)
                ELSE 0
            END AS total_margin_percent,
            %(currency)s AS currency
        FROM `tabNDIS Cost Allocation Entry` cae
        {build_where(conditions)}
        GROUP BY COALESCE(NULLIF(cae.house, ''), 'Unassigned'), COALESCE(NULLIF(cae.participant, ''), 'Unassigned')
        ORDER BY margin_after_all_costs ASC
        """,
        params,
        as_dict=True,
    )
    chart = {
        "data": {
            "labels": [f"{row.house} / {row.participant}" for row in data[:20]],
            "datasets": [
                {"name": "Paid Revenue", "values": [flt(row.paid_revenue) for row in data[:20]]},
                {"name": "Payroll Cost", "values": [flt(row.payroll_cost) for row in data[:20]]},
                {"name": "Total Cost", "values": [flt(row.total_allocated_cost) for row in data[:20]]},
            ],
        },
        "type": "bar",
    }
    summary = [
        summary_item(sum(flt(row.paid_revenue) for row in data), "Paid Revenue", "Currency", "Green"),
        summary_item(sum(flt(row.payroll_cost) for row in data), "Payroll Cost", "Currency", "Orange"),
        summary_item(sum(flt(row.total_allocated_cost) for row in data), "Total Allocated Cost", "Currency", "Orange"),
        summary_item(sum(flt(row.margin_after_all_costs) for row in data), "Margin After All Costs", "Currency", "Green"),
    ]

    return columns, data, None, chart, summary


def add_general_allocation_filters(filters):
    conditions = ["cae.status = 'Active'"]
    params = {}

    from_date = get_filter(filters, "from_date")
    to_date = get_filter(filters, "to_date")
    if from_date:
        conditions.append("cae.period_end >= %(from_date)s")
        params["from_date"] = from_date
    if to_date:
        conditions.append("cae.period_start <= %(to_date)s")
        params["to_date"] = to_date

    for key in ["company", "house", "participant"]:
        value = get_filter(filters, key)
        if value:
            conditions.append(f"cae.{key} = %({key})s")
            params[key] = value

    return conditions, params


def col(fieldname, label, fieldtype, options=None, width=120):
    row = {
        "fieldname": fieldname,
        "label": _(label),
        "fieldtype": fieldtype,
        "width": width,
    }
    if options:
        row["options"] = options
    return row


def money_col(fieldname, label, width=140):
    return col(fieldname, label, "Currency", "currency", width)


def currency_col():
    row = col("currency", "Currency", "Link", "Currency", 80)
    row["hidden"] = 1
    return row


def bar_chart(data, label_field, datasets):
    return {
        "data": {
            "labels": [row.get(label_field) for row in data[:20]],
            "datasets": [
                {"name": name, "values": [flt(row.get(fieldname)) for row in data[:20]]}
                for name, fieldname in datasets
            ],
        },
        "type": "bar",
    }


def summary_item(value, label, datatype, indicator):
    row = {
        "value": value,
        "indicator": indicator,
        "label": _(label),
        "datatype": datatype,
    }
    if datatype == "Currency":
        row["currency"] = currency()
    return row


@frappe.whitelist()
def quick_payroll_profitability_summary():
    imported = frappe.db.sql(
        """
        SELECT
            COUNT(*) AS import_count,
            COALESCE(SUM(total_import_cost_amount), 0) AS total_import_cost_amount,
            COALESCE(SUM(unmapped_line_count), 0) AS unmapped_line_count,
            COALESCE(SUM(cost_pool_count), 0) AS cost_pool_count,
            COALESCE(SUM(allocated_cost_pool_count), 0) AS allocated_cost_pool_count
        FROM `tabNDIS Payroll Cost Import`
        WHERE status != 'Cancelled'
        """,
        as_dict=True,
    )[0]
    allocated = frappe.db.sql(
        """
        SELECT
            COALESCE(SUM(cae.allocated_cost_amount), 0) AS allocated_payroll_cost,
            COUNT(*) AS allocation_entry_count
        FROM `tabNDIS Cost Allocation Entry` cae
        INNER JOIN `tabNDIS Cost Pool` cp ON cp.name = cae.cost_pool
        WHERE cae.status = 'Active'
        AND cae.cost_type = 'Payroll'
        """,
        as_dict=True,
    )[0]

    return {
        "today": today(),
        "imports": imported,
        "allocated": allocated,
        "top_houses_by_payroll_cost": top_payroll_cost("house"),
        "top_participants_by_payroll_cost": top_payroll_cost("participant"),
        "note": "Payroll profitability summary only. No Payment Entry, Journal Entry, GL Entry, payroll posting, STP, ABA, or accounting movement created.",
    }


def top_payroll_cost(fieldname):
    return frappe.db.sql(
        f"""
        SELECT
            COALESCE(NULLIF(cae.{fieldname}, ''), 'Unassigned') AS {fieldname},
            COALESCE(SUM(cae.allocated_cost_amount), 0) AS payroll_cost
        FROM `tabNDIS Cost Allocation Entry` cae
        INNER JOIN `tabNDIS Cost Pool` cp ON cp.name = cae.cost_pool
        WHERE cae.status = 'Active'
        AND cae.cost_type = 'Payroll'
        GROUP BY COALESCE(NULLIF(cae.{fieldname}, ''), 'Unassigned')
        ORDER BY payroll_cost DESC
        LIMIT 10
        """,
        as_dict=True,
    )
