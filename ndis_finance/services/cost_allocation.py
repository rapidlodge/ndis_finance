import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime

from ndis_finance.services.permissions import assert_action


def make_cost_pool_id(cost_type="Other"):
    prefix = "NDIS-COST"

    if cost_type:
        prefix = "NDIS-COST-" + frappe.scrub(cost_type).replace("_", "-").upper()

    timestamp = get_datetime().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{timestamp}-{frappe.generate_hash(length=5).upper()}"


def safe_db_set(doctype, name, fieldname, value):
    if name and frappe.get_meta(doctype).has_field(fieldname):
        frappe.db.set_value(doctype, name, fieldname, value, update_modified=False)


@frappe.whitelist()
def create_cost_pool(
    cost_type="Other",
    allocation_method="Equal Participant Split",
    company=None,
    house=None,
    participant=None,
    cost_center=None,
    period_start=None,
    period_end=None,
    total_cost_amount=0,
    source_doctype=None,
    source_name=None,
    source_reference=None,
    notes=None,
):
    assert_action("manage_cost_pool")

    if not period_start or not period_end:
        frappe.throw(_("Period Start and Period End are required."))

    if period_end < period_start:
        frappe.throw(_("Period End cannot be before Period Start."))

    if flt(total_cost_amount) <= 0:
        frappe.throw(_("Total Cost Amount must be greater than zero."))

    house_methods = [
        "Equal Participant Split",
        "Claim Amount Share",
        "Paid Amount Share",
        "House Only",
    ]

    if allocation_method in house_methods and not house:
        frappe.throw(_("House is required for this allocation method."))

    if allocation_method == "Direct Participant" and not participant:
        frappe.throw(_("Participant is required for Direct Participant allocation."))

    if house and not cost_center:
        cost_center = frappe.db.get_value("NDIS House", house, "custom_ndis_cost_center")

    doc = frappe.new_doc("NDIS Cost Pool")
    doc.cost_pool_id = make_cost_pool_id(cost_type)
    doc.status = "Draft"
    doc.cost_type = cost_type
    doc.allocation_method = allocation_method
    doc.company = company
    doc.house = house
    doc.participant = participant
    doc.cost_center = cost_center
    doc.period_start = period_start
    doc.period_end = period_end
    doc.total_cost_amount = flt(total_cost_amount)
    doc.allocated_amount = 0
    doc.unallocated_amount = flt(total_cost_amount)
    doc.allocation_count = 0
    doc.source_doctype = source_doctype
    doc.source_name = source_name
    doc.source_reference = source_reference
    doc.notes = notes
    doc.insert(ignore_permissions=True)

    frappe.db.commit()

    return {
        "created": True,
        "cost_pool": doc.name,
        "cost_pool_id": doc.cost_pool_id,
        "allocation_method": doc.allocation_method,
        "total_cost_amount": flt(doc.total_cost_amount),
        "note": "Cost pool created only. No accounting entry was created.",
    }


@frappe.whitelist()
def allocate_cost_pool(cost_pool, replace_existing=1):
    assert_action("allocate_cost_pool")

    if not frappe.db.exists("NDIS Cost Pool", cost_pool):
        frappe.throw(_("NDIS Cost Pool not found: {0}").format(cost_pool))

    pool = frappe.get_doc("NDIS Cost Pool", cost_pool)

    if pool.status == "Cancelled":
        frappe.throw(_("Cancelled cost pools cannot be allocated."))

    if int(replace_existing or 0):
        cancel_existing_entries(cost_pool)

    basis_rows = get_allocation_basis(pool)
    if not basis_rows:
        frappe.throw(_("No allocation basis rows found for this cost pool."))

    total_basis = sum(flt(row.get("basis_amount")) for row in basis_rows)
    flat_methods = ["Equal Participant Split", "Direct Participant", "House Only"]

    if pool.allocation_method in flat_methods:
        total_basis = len(basis_rows)

    if total_basis <= 0:
        frappe.throw(_("Allocation basis total is zero."))

    created = []
    total_allocated = 0

    for row in basis_rows:
        if pool.allocation_method in flat_methods:
            allocation_percent = 100 / len(basis_rows)
        else:
            allocation_percent = (flt(row.get("basis_amount")) / total_basis) * 100

        allocated_amount = round(flt(pool.total_cost_amount) * allocation_percent / 100, 2)
        total_allocated += allocated_amount

        entry = frappe.new_doc("NDIS Cost Allocation Entry")
        entry.cost_pool = pool.name
        entry.status = "Active"
        entry.cost_type = pool.cost_type
        entry.allocation_method = pool.allocation_method
        entry.company = pool.company
        entry.house = row.get("house") or pool.house
        entry.participant = row.get("participant")
        entry.period_start = pool.period_start
        entry.period_end = pool.period_end
        entry.gross_claim_amount = flt(row.get("gross_claim_amount"))
        entry.paid_amount = flt(row.get("paid_amount"))
        entry.claim_line_count = int(row.get("claim_line_count") or 0)
        entry.allocation_basis_amount = flt(row.get("basis_amount"))
        entry.allocation_percent = allocation_percent
        entry.allocated_cost_amount = allocated_amount
        entry.estimated_margin_amount = flt(row.get("paid_amount")) - allocated_amount
        entry.estimated_margin_percent = calculate_margin_percent(
            revenue=flt(row.get("paid_amount")),
            cost=allocated_amount,
        )
        entry.allocation_note = row.get("note")
        entry.insert(ignore_permissions=True)

        created.append(entry.name)

    rounding_diff = round(flt(pool.total_cost_amount) - total_allocated, 2)
    if created and abs(rounding_diff) >= 0.01:
        last = frappe.get_doc("NDIS Cost Allocation Entry", created[-1])
        last.allocated_cost_amount = flt(last.allocated_cost_amount) + rounding_diff
        last.estimated_margin_amount = flt(last.paid_amount) - flt(
            last.allocated_cost_amount
        )
        last.estimated_margin_percent = calculate_margin_percent(
            revenue=flt(last.paid_amount),
            cost=flt(last.allocated_cost_amount),
        )
        last.save(ignore_permissions=True)

    refresh_cost_pool_summary(pool.name)

    frappe.db.set_value(
        "NDIS Cost Pool",
        pool.name,
        {
            "status": "Allocated",
            "allocated_on": now_datetime(),
            "allocated_by": frappe.session.user,
        },
        update_modified=False,
    )

    frappe.db.commit()

    return {
        "cost_pool": pool.name,
        "created_entries": len(created),
        "allocated_amount": flt(pool.total_cost_amount),
        "entries": created[:20],
        "note": "Cost allocation entries created for management reporting only. No GL, Journal Entry, Payment Entry, or payroll posting was created.",
    }


def get_allocation_basis(pool):
    if pool.allocation_method == "Direct Participant":
        return [
            {
                "house": pool.house,
                "participant": pool.participant,
                "gross_claim_amount": 0,
                "paid_amount": 0,
                "claim_line_count": 0,
                "basis_amount": 1,
                "note": "Direct participant allocation.",
            }
        ]

    if pool.allocation_method == "House Only":
        return [
            {
                "house": pool.house,
                "participant": None,
                "gross_claim_amount": 0,
                "paid_amount": 0,
                "claim_line_count": 0,
                "basis_amount": 1,
                "note": "House-only allocation.",
            }
        ]

    rows = frappe.db.sql(
        """
        SELECT
            cl.house,
            cl.participant,
            COUNT(*) AS claim_line_count,
            COALESCE(SUM(cl.claim_amount), 0) AS gross_claim_amount,
            COALESCE(SUM(cl.paid_amount), 0) AS paid_amount
        FROM `tabNDIS Claim Line` cl
        WHERE cl.house = %(house)s
            AND cl.service_date >= %(period_start)s
            AND cl.service_date <= %(period_end)s
            AND cl.participant IS NOT NULL
            AND cl.participant != ''
        GROUP BY cl.house, cl.participant
        ORDER BY gross_claim_amount DESC
        """,
        {
            "house": pool.house,
            "period_start": pool.period_start,
            "period_end": pool.period_end,
        },
        as_dict=True,
    )

    output = []

    for row in rows:
        if pool.allocation_method == "Equal Participant Split":
            basis_amount = 1
            note = "Equal split between participants with claim activity in the period."
        elif pool.allocation_method == "Claim Amount Share":
            basis_amount = flt(row.gross_claim_amount)
            note = "Allocated by participant claim amount share."
        elif pool.allocation_method == "Paid Amount Share":
            basis_amount = flt(row.paid_amount)
            note = "Allocated by participant paid amount share."
        else:
            basis_amount = 0
            note = "Unsupported method."

        output.append(
            {
                "house": row.house,
                "participant": row.participant,
                "gross_claim_amount": flt(row.gross_claim_amount),
                "paid_amount": flt(row.paid_amount),
                "claim_line_count": int(row.claim_line_count or 0),
                "basis_amount": basis_amount,
                "note": note,
            }
        )

    return output


def cancel_existing_entries(cost_pool):
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
                "allocation_note": "Cancelled/replaced by re-allocation.",
            },
            update_modified=False,
        )


@frappe.whitelist()
def cancel_cost_pool(cost_pool, reason=None):
    assert_action("cancel_cost_pool")

    if not frappe.db.exists("NDIS Cost Pool", cost_pool):
        frappe.throw(_("NDIS Cost Pool not found: {0}").format(cost_pool))

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
                "allocation_note": reason or "Cost pool cancelled.",
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
            "warning_log": reason or "Cost pool cancelled.",
        },
        update_modified=False,
    )

    refresh_cost_pool_summary(cost_pool)

    frappe.db.commit()

    return {
        "cost_pool": cost_pool,
        "status": "Cancelled",
        "cancelled_entries": len(entries),
        "note": "Cost pool cancelled for management reporting only. No accounting reversal was created.",
    }


@frappe.whitelist()
def refresh_cost_pool_summary(cost_pool):
    rows = frappe.db.sql(
        """
        SELECT
            COUNT(*) AS allocation_count,
            COALESCE(SUM(allocated_cost_amount), 0) AS allocated_amount
        FROM `tabNDIS Cost Allocation Entry`
        WHERE cost_pool = %(cost_pool)s
            AND status = 'Active'
        """,
        {"cost_pool": cost_pool},
        as_dict=True,
    )

    totals = rows[0] if rows else {}
    total_cost = flt(
        frappe.db.get_value("NDIS Cost Pool", cost_pool, "total_cost_amount") or 0
    )
    allocated = flt(totals.get("allocated_amount"))

    frappe.db.set_value(
        "NDIS Cost Pool",
        cost_pool,
        {
            "allocation_count": int(totals.get("allocation_count") or 0),
            "allocated_amount": allocated,
            "unallocated_amount": total_cost - allocated,
        },
        update_modified=False,
    )

    return {
        "cost_pool": cost_pool,
        "allocation_count": int(totals.get("allocation_count") or 0),
        "allocated_amount": allocated,
        "unallocated_amount": total_cost - allocated,
    }


def calculate_margin_percent(revenue, cost):
    revenue = flt(revenue)
    cost = flt(cost)

    if revenue <= 0:
        return 0

    return round(((revenue - cost) / revenue) * 100, 2)


@frappe.whitelist()
def quick_cost_allocation_summary(limit=20):
    pools = frappe.get_all(
        "NDIS Cost Pool",
        fields=[
            "name",
            "cost_pool_id",
            "status",
            "cost_type",
            "allocation_method",
            "company",
            "house",
            "participant",
            "period_start",
            "period_end",
            "total_cost_amount",
            "allocated_amount",
            "unallocated_amount",
            "allocation_count",
        ],
        order_by="modified desc",
        limit=int(limit or 20),
    )

    entries = frappe.get_all(
        "NDIS Cost Allocation Entry",
        fields=[
            "name",
            "cost_pool",
            "status",
            "cost_type",
            "allocation_method",
            "house",
            "participant",
            "period_start",
            "period_end",
            "gross_claim_amount",
            "paid_amount",
            "allocated_cost_amount",
            "estimated_margin_amount",
            "estimated_margin_percent",
        ],
        order_by="modified desc",
        limit=int(limit or 20),
    )

    return {
        "cost_pools": pools,
        "allocation_entries": entries,
        "note": "Cost allocation summary only. No GL, Journal Entry, Payment Entry, payroll posting, or accounting movement created.",
    }
