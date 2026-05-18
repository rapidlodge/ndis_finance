import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime

from ndis_finance.services.cost_allocation import allocate_cost_pool
from ndis_finance.services.permissions import assert_action


VALID_COST_BASIS = {
    "Gross + Employer Super",
    "Gross Only",
    "Employer Super Only",
    "Estimated Net Pay Only",
}


def make_import_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-PAYROLL-COST-{timestamp}-{frappe.generate_hash(length=5).upper()}"


def make_cost_pool_id():
    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"NDIS-COST-PAYROLL-{timestamp}-{frappe.generate_hash(length=5).upper()}"


def safe_db_set(doctype, name, fieldname, value):
    if name and frappe.get_meta(doctype).has_field(fieldname):
        frappe.db.set_value(doctype, name, fieldname, value, update_modified=False)


def get_import_cost_amount(row, cost_basis):
    if cost_basis not in VALID_COST_BASIS:
        frappe.throw(_("Unsupported payroll cost basis: {0}").format(cost_basis))

    gross = flt(row.get("gross_amount"))
    super_liability = flt(row.get("employer_super_liability"))
    net_pay = flt(row.get("estimated_net_pay"))

    if cost_basis == "Gross Only":
        return gross
    if cost_basis == "Employer Super Only":
        return super_liability
    if cost_basis == "Estimated Net Pay Only":
        return net_pay

    return gross + super_liability


def get_employee_house(employee, default_house=None):
    if not employee:
        return default_house

    house = None
    if frappe.get_meta("Employee").has_field("custom_ndis_default_house"):
        house = frappe.db.get_value("Employee", employee, "custom_ndis_default_house")

    return house or default_house


def get_employee_costing_enabled(employee):
    if not employee:
        return 1

    if frappe.get_meta("Employee").has_field("custom_ndis_payroll_costing_enabled"):
        value = frappe.db.get_value(
            "Employee",
            employee,
            "custom_ndis_payroll_costing_enabled",
        )
        return int(value if value is not None else 1)

    return 1


def get_employee_allocation_method(employee, fallback):
    if not employee:
        return fallback

    if frappe.get_meta("Employee").has_field("custom_ndis_payroll_cost_allocation_method"):
        value = frappe.db.get_value(
            "Employee",
            employee,
            "custom_ndis_payroll_cost_allocation_method",
        )
        return value or fallback

    return fallback


def fetch_au_payroll_run_details(au_payroll_run_log):
    if not frappe.db.exists("AU Payroll Run Log", au_payroll_run_log):
        frappe.throw(_("AU Payroll Run Log not found: {0}").format(au_payroll_run_log))

    run = frappe.get_doc("AU Payroll Run Log", au_payroll_run_log)
    rows = frappe.db.sql(
        """
        SELECT
            name,
            parent,
            employee,
            employee_name,
            salary_slip,
            gross_amount,
            payg_amount,
            stsl_amount,
            total_withholding_amount,
            employer_super_liability,
            estimated_net_pay,
            row_status,
            payroll_safe_to_use
        FROM `tabAU Payroll Run Detail`
        WHERE parent = %(parent)s
        ORDER BY idx ASC, name ASC
        """,
        {"parent": au_payroll_run_log},
        as_dict=True,
    )

    return run, rows


@frappe.whitelist()
def preview_payroll_cost_import(
    au_payroll_run_log,
    cost_basis="Gross + Employer Super",
    allocation_method="Paid Amount Share",
    default_house=None,
    include_only_payroll_safe_rows=1,
    limit=20,
):
    run, rows = fetch_au_payroll_run_details(au_payroll_run_log)
    preview_rows = []
    totals = empty_totals()

    for row in rows:
        mapped_row = prepare_import_line_row(
            row=row,
            cost_basis=cost_basis,
            allocation_method=allocation_method,
            default_house=default_house,
            include_only_payroll_safe_rows=include_only_payroll_safe_rows,
        )

        if mapped_row.get("skip"):
            totals["skipped_line_count"] += 1
            continue

        add_to_totals(totals, mapped_row)
        preview_rows.append(mapped_row)

    return {
        "au_payroll_run_log": au_payroll_run_log,
        "company": run.company,
        "period_start": run.from_date,
        "period_end": run.to_date,
        "cost_basis": cost_basis,
        "allocation_method": allocation_method,
        "totals": totals,
        "preview": preview_rows[: int(limit or 20)],
        "note": "Preview only. No import, cost pool, allocation entry, payroll posting, STP, ABA, or accounting movement created.",
    }


def empty_totals():
    return {
        "line_count": 0,
        "mapped_line_count": 0,
        "unmapped_line_count": 0,
        "skipped_line_count": 0,
        "total_gross_amount": 0,
        "total_employer_super_liability": 0,
        "total_estimated_net_pay": 0,
        "total_import_cost_amount": 0,
    }


def prepare_import_line_row(
    row,
    cost_basis,
    allocation_method,
    default_house=None,
    include_only_payroll_safe_rows=1,
):
    employee = row.get("employee")
    payroll_safe = int(row.get("payroll_safe_to_use") or 0)

    if int(include_only_payroll_safe_rows or 0) and not payroll_safe:
        return {"skip": True, "skip_reason": "Unsafe payroll row", "employee": employee}

    if not get_employee_costing_enabled(employee):
        return {
            "skip": True,
            "skip_reason": "Employee NDIS payroll costing disabled",
            "employee": employee,
        }

    house = get_employee_house(employee, default_house)
    method = get_employee_allocation_method(employee, allocation_method)
    import_cost = get_import_cost_amount(row, cost_basis)

    return {
        "skip": False,
        "employee": employee,
        "employee_name": row.get("employee_name"),
        "salary_slip": row.get("salary_slip"),
        "house": house,
        "allocation_method": method,
        "gross_amount": flt(row.get("gross_amount")),
        "employer_super_liability": flt(row.get("employer_super_liability")),
        "estimated_net_pay": flt(row.get("estimated_net_pay")),
        "import_cost_amount": import_cost,
        "payroll_safe_to_use": payroll_safe,
        "row_status": row.get("row_status"),
        "au_payroll_run_detail_row": row.get("name"),
        "mapping_status": "Mapped" if house else "Unmapped",
    }


def add_to_totals(totals, row):
    mapped = bool(row.get("house"))
    totals["line_count"] += 1
    totals["mapped_line_count"] += 1 if mapped else 0
    totals["unmapped_line_count"] += 0 if mapped else 1
    totals["total_gross_amount"] += flt(row.get("gross_amount"))
    totals["total_employer_super_liability"] += flt(
        row.get("employer_super_liability")
    )
    totals["total_estimated_net_pay"] += flt(row.get("estimated_net_pay"))
    totals["total_import_cost_amount"] += flt(row.get("import_cost_amount"))


@frappe.whitelist()
def import_payroll_costs(
    au_payroll_run_log,
    cost_basis="Gross + Employer Super",
    allocation_method="Paid Amount Share",
    default_house=None,
    include_only_payroll_safe_rows=1,
    auto_allocate_cost_pools=0,
    replace_existing=0,
    dry_run=0,
    notes=None,
):
    assert_action("import_payroll_costs")

    if int(dry_run or 0):
        return preview_payroll_cost_import(
            au_payroll_run_log=au_payroll_run_log,
            cost_basis=cost_basis,
            allocation_method=allocation_method,
            default_house=default_house,
            include_only_payroll_safe_rows=include_only_payroll_safe_rows,
        )

    run, rows = fetch_au_payroll_run_details(au_payroll_run_log)
    cancel_existing_import_if_requested(au_payroll_run_log, replace_existing)

    doc = frappe.new_doc("NDIS Payroll Cost Import")
    doc.import_id = make_import_id()
    doc.status = "Imported"
    doc.au_payroll_run_log = au_payroll_run_log
    doc.company = run.company
    doc.period_start = run.from_date
    doc.period_end = run.to_date
    doc.default_house = default_house
    doc.cost_basis = cost_basis
    doc.allocation_method = allocation_method
    doc.include_only_payroll_safe_rows = int(include_only_payroll_safe_rows or 0)
    doc.auto_allocate_cost_pools = int(auto_allocate_cost_pools or 0)
    doc.replace_existing = int(replace_existing or 0)
    doc.imported_on = now_datetime()
    doc.imported_by = frappe.session.user
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    created_lines = []
    warning_log = []

    for row in rows:
        mapped_row = prepare_import_line_row(
            row=row,
            cost_basis=cost_basis,
            allocation_method=allocation_method,
            default_house=default_house,
            include_only_payroll_safe_rows=include_only_payroll_safe_rows,
        )

        if mapped_row.get("skip"):
            warning_log.append(
                f"Skipped {mapped_row.get('employee')}: {mapped_row.get('skip_reason')}"
            )
            continue

        line = create_import_line(doc, au_payroll_run_log, mapped_row)
        created_lines.append(line.name)

        if line.house and flt(line.import_cost_amount) > 0:
            cost_pool = create_payroll_cost_pool_from_import_line(doc, line)
            line.status = "Cost Pool Created"
            line.cost_pool = cost_pool
            line.save(ignore_permissions=True)

            if int(auto_allocate_cost_pools or 0):
                allocate_cost_pool_from_line(line, cost_pool, warning_log)

    refresh_payroll_cost_import_summary(doc.name)
    final_status = set_final_import_status(doc.name, auto_allocate_cost_pools, warning_log)
    frappe.db.commit()

    return {
        "created": True,
        "payroll_cost_import": doc.name,
        "import_id": doc.import_id,
        "line_count": len(created_lines),
        "cost_pool_count": frappe.db.count(
            "NDIS Payroll Cost Import Line",
            {"payroll_cost_import": doc.name, "cost_pool": ["is", "set"]},
        ),
        "allocated_cost_pool_count": frappe.db.count(
            "NDIS Payroll Cost Import Line",
            {"payroll_cost_import": doc.name, "status": "Allocated"},
        ),
        "status": final_status,
        "note": "Payroll costs imported into NDIS management cost pools only. No Payment Entry, Journal Entry, GL Entry, payroll posting, STP, ABA, or accounting movement was created.",
    }


def cancel_existing_import_if_requested(au_payroll_run_log, replace_existing):
    existing = frappe.get_all(
        "NDIS Payroll Cost Import",
        filters={
            "au_payroll_run_log": au_payroll_run_log,
            "status": ["!=", "Cancelled"],
        },
        fields=["name"],
        limit=1,
    )

    if existing and not int(replace_existing or 0):
        frappe.throw(
            _(
                "A non-cancelled NDIS Payroll Cost Import already exists for this AU Payroll Run Log: {0}. Use replace_existing=1 if this is intentional."
            ).format(existing[0].name)
        )

    if existing and int(replace_existing or 0):
        cancel_payroll_cost_import(
            payroll_cost_import=existing[0].name,
            reason="Cancelled by replace_existing import.",
            ignore_permissions=True,
        )


def create_import_line(import_doc, au_payroll_run_log, mapped_row):
    line = frappe.new_doc("NDIS Payroll Cost Import Line")
    line.payroll_cost_import = import_doc.name
    line.status = "Mapped" if mapped_row.get("house") else "Unmapped"
    line.au_payroll_run_log = au_payroll_run_log
    line.au_payroll_run_detail_row = mapped_row.get("au_payroll_run_detail_row")
    line.employee = mapped_row.get("employee")
    line.employee_name = mapped_row.get("employee_name")
    line.salary_slip = mapped_row.get("salary_slip")
    line.payroll_safe_to_use = mapped_row.get("payroll_safe_to_use")
    line.row_status = mapped_row.get("row_status")
    line.house = mapped_row.get("house")
    line.allocation_method = mapped_row.get("allocation_method")
    line.gross_amount = flt(mapped_row.get("gross_amount"))
    line.employer_super_liability = flt(mapped_row.get("employer_super_liability"))
    line.estimated_net_pay = flt(mapped_row.get("estimated_net_pay"))
    line.import_cost_amount = flt(mapped_row.get("import_cost_amount"))
    line.mapping_note = (
        "Mapped to employee/default import house."
        if line.house
        else "No NDIS House mapped."
    )
    line.insert(ignore_permissions=True)
    return line


def allocate_cost_pool_from_line(line, cost_pool, warning_log):
    try:
        allocate_cost_pool(cost_pool=cost_pool, replace_existing=1)
        line.status = "Allocated"
        line.save(ignore_permissions=True)
    except Exception as exc:
        line.status = "Error"
        line.error_log = str(exc)
        line.save(ignore_permissions=True)
        warning_log.append(f"Allocation failed for {line.name}: {str(exc)}")


def set_final_import_status(payroll_cost_import, auto_allocate_cost_pools, warning_log):
    allocated_count = frappe.db.count(
        "NDIS Payroll Cost Import Line",
        {"payroll_cost_import": payroll_cost_import, "status": "Allocated"},
    )
    cost_pool_count = frappe.db.count(
        "NDIS Payroll Cost Import Line",
        {
            "payroll_cost_import": payroll_cost_import,
            "status": ["in", ["Cost Pool Created", "Allocated", "Error"]],
        },
    )

    final_status = "Imported"
    updates = {"warning_log": "\n".join(warning_log[:200])}

    if int(auto_allocate_cost_pools or 0) and allocated_count and allocated_count == cost_pool_count:
        final_status = "Allocated"
        updates["allocated_on"] = now_datetime()
    elif int(auto_allocate_cost_pools or 0) and warning_log and not allocated_count:
        final_status = "Failed"
    elif int(auto_allocate_cost_pools or 0) and allocated_count:
        final_status = "Partially Allocated"
    elif warning_log and not cost_pool_count:
        final_status = "Failed"

    updates["status"] = final_status
    frappe.db.set_value(
        "NDIS Payroll Cost Import",
        payroll_cost_import,
        updates,
        update_modified=False,
    )
    return final_status


def create_payroll_cost_pool_from_import_line(import_doc, line):
    pool = frappe.new_doc("NDIS Cost Pool")
    pool.cost_pool_id = make_cost_pool_id()
    pool.status = "Draft"
    pool.cost_type = "Payroll"
    pool.allocation_method = line.allocation_method or import_doc.allocation_method
    pool.company = import_doc.company
    pool.house = line.house
    pool.period_start = import_doc.period_start
    pool.period_end = import_doc.period_end
    pool.total_cost_amount = flt(line.import_cost_amount)
    pool.allocated_amount = 0
    pool.unallocated_amount = flt(line.import_cost_amount)
    pool.allocation_count = 0
    pool.source_doctype = "AU Payroll Run Log"
    pool.source_name = import_doc.au_payroll_run_log
    pool.source_reference = f"Employee {line.employee} / Salary Slip {line.salary_slip or ''}".strip()
    pool.notes = (
        f"Created from NDIS Payroll Cost Import {import_doc.name}. "
        "Management costing only."
    )
    pool.insert(ignore_permissions=True)

    safe_db_set("NDIS Cost Pool", pool.name, "payroll_cost_import", import_doc.name)
    safe_db_set("NDIS Cost Pool", pool.name, "payroll_cost_import_line", line.name)
    safe_db_set("NDIS Cost Pool", pool.name, "au_payroll_run_log", import_doc.au_payroll_run_log)
    return pool.name


@frappe.whitelist()
def cancel_payroll_cost_import(payroll_cost_import, reason=None, ignore_permissions=False):
    if not ignore_permissions:
        assert_action("cancel_payroll_cost_import")

    if not frappe.db.exists("NDIS Payroll Cost Import", payroll_cost_import):
        frappe.throw(
            _("NDIS Payroll Cost Import not found: {0}").format(payroll_cost_import)
        )

    lines = frappe.get_all(
        "NDIS Payroll Cost Import Line",
        filters={
            "payroll_cost_import": payroll_cost_import,
            "status": ["!=", "Cancelled"],
        },
        fields=["name", "cost_pool"],
    )

    for line in lines:
        if line.cost_pool and frappe.db.exists("NDIS Cost Pool", line.cost_pool):
            cancel_cost_pool_control_only(
                line.cost_pool,
                reason or "Payroll cost import cancelled.",
            )

        frappe.db.set_value(
            "NDIS Payroll Cost Import Line",
            line.name,
            {
                "status": "Cancelled",
                "mapping_note": reason or "Payroll cost import cancelled.",
            },
            update_modified=False,
        )

    frappe.db.set_value(
        "NDIS Payroll Cost Import",
        payroll_cost_import,
        {
            "status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "warning_log": reason or "Payroll cost import cancelled.",
        },
        update_modified=False,
    )
    refresh_payroll_cost_import_summary(payroll_cost_import)
    frappe.db.commit()

    return {
        "payroll_cost_import": payroll_cost_import,
        "status": "Cancelled",
        "cancelled_lines": len(lines),
        "note": "Payroll cost import cancelled for management costing only. No accounting reversal was created.",
    }


def cancel_cost_pool_control_only(cost_pool, reason):
    entries = frappe.get_all(
        "NDIS Cost Allocation Entry",
        filters={"cost_pool": cost_pool, "status": "Active"},
        fields=["name"],
    )

    for entry in entries:
        frappe.db.set_value(
            "NDIS Cost Allocation Entry",
            entry.name,
            {
                "status": "Cancelled",
                "allocation_note": reason,
            },
            update_modified=False,
        )

    frappe.db.set_value(
        "NDIS Cost Pool",
        cost_pool,
        {
            "status": "Cancelled",
            "cancelled_on": now_datetime(),
            "cancelled_by": frappe.session.user,
            "warning_log": reason,
        },
        update_modified=False,
    )


@frappe.whitelist()
def refresh_payroll_cost_import_summary(payroll_cost_import):
    rows = frappe.db.sql(
        """
        SELECT
            COUNT(*) AS line_count,
            COALESCE(SUM(CASE WHEN status IN ('Mapped', 'Cost Pool Created', 'Allocated') THEN 1 ELSE 0 END), 0) AS mapped_line_count,
            COALESCE(SUM(CASE WHEN status = 'Unmapped' THEN 1 ELSE 0 END), 0) AS unmapped_line_count,
            COALESCE(SUM(CASE WHEN cost_pool IS NOT NULL AND cost_pool != '' THEN 1 ELSE 0 END), 0) AS cost_pool_count,
            COALESCE(SUM(CASE WHEN status = 'Allocated' THEN 1 ELSE 0 END), 0) AS allocated_cost_pool_count,
            COALESCE(SUM(gross_amount), 0) AS total_gross_amount,
            COALESCE(SUM(employer_super_liability), 0) AS total_employer_super_liability,
            COALESCE(SUM(estimated_net_pay), 0) AS total_estimated_net_pay,
            COALESCE(SUM(import_cost_amount), 0) AS total_import_cost_amount
        FROM `tabNDIS Payroll Cost Import Line`
        WHERE payroll_cost_import = %(payroll_cost_import)s
        AND status != 'Cancelled'
        """,
        {"payroll_cost_import": payroll_cost_import},
        as_dict=True,
    )

    totals = rows[0] if rows else {}
    update = {
        "line_count": int(totals.get("line_count") or 0),
        "mapped_line_count": int(totals.get("mapped_line_count") or 0),
        "unmapped_line_count": int(totals.get("unmapped_line_count") or 0),
        "cost_pool_count": int(totals.get("cost_pool_count") or 0),
        "allocated_cost_pool_count": int(
            totals.get("allocated_cost_pool_count") or 0
        ),
        "total_gross_amount": flt(totals.get("total_gross_amount")),
        "total_employer_super_liability": flt(
            totals.get("total_employer_super_liability")
        ),
        "total_estimated_net_pay": flt(totals.get("total_estimated_net_pay")),
        "total_import_cost_amount": flt(totals.get("total_import_cost_amount")),
    }

    frappe.db.set_value(
        "NDIS Payroll Cost Import",
        payroll_cost_import,
        update,
        update_modified=False,
    )
    update["payroll_cost_import"] = payroll_cost_import
    return update


@frappe.whitelist()
def quick_payroll_cost_import_summary(limit=20):
    imports = frappe.get_all(
        "NDIS Payroll Cost Import",
        fields=[
            "name",
            "import_id",
            "status",
            "au_payroll_run_log",
            "company",
            "period_start",
            "period_end",
            "cost_basis",
            "allocation_method",
            "line_count",
            "mapped_line_count",
            "unmapped_line_count",
            "cost_pool_count",
            "allocated_cost_pool_count",
            "total_import_cost_amount",
        ],
        order_by="modified desc",
        limit=int(limit or 20),
    )
    lines = frappe.get_all(
        "NDIS Payroll Cost Import Line",
        fields=[
            "name",
            "payroll_cost_import",
            "status",
            "au_payroll_run_log",
            "employee",
            "employee_name",
            "salary_slip",
            "house",
            "cost_pool",
            "gross_amount",
            "employer_super_liability",
            "estimated_net_pay",
            "import_cost_amount",
        ],
        order_by="modified desc",
        limit=int(limit or 20),
    )

    return {
        "imports": imports,
        "lines": lines,
        "note": "Payroll cost bridge summary only. No GL, Journal Entry, Payment Entry, payroll posting, STP, ABA, or accounting movement created.",
    }
