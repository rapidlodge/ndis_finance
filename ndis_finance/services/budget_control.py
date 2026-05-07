import frappe
from frappe import _
from frappe.utils import flt, getdate, now_datetime, today

from ndis_finance.services.permissions import assert_action


def validate_budget_and_service_booking(doc):
    """
    NDIS budget and service-booking validation.

    This function:
    - Does not create GL Entries.
    - Does not edit submitted accounting records.
    - Runs on Sales Invoice validate.
    - Links invoice rows to the best matching NDIS Plan Budget and Service Booking.
    - Warns or blocks depending on the control mode.
    """

    if not getattr(doc, "custom_is_ndis_invoice", 0):
        return

    budget_mode = getattr(doc, "custom_ndis_budget_control_mode", None) or "Warn Only"
    booking_mode = getattr(doc, "custom_ndis_service_booking_control_mode", None) or "Warn Only"

    if budget_mode == "Disabled" and booking_mode == "Disabled":
        set_doc_field(doc, "custom_ndis_validation_status", "Passed")
        set_doc_field(doc, "custom_ndis_validation_last_run", now_datetime())
        mark_disabled(doc)
        return

    warnings = []
    blockers = []

    budget_current_usage = {}
    booking_current_usage = {}

    for row in doc.items:
        if not getattr(row, "custom_ndis_claimable", 0):
            continue

        row_amount = get_row_amount(row)
        participant = getattr(row, "custom_ndis_participant", None) or doc.customer
        service_date = getattr(row, "custom_ndis_service_date", None)
        support_item = getattr(row, "custom_ndis_support_item", None)
        service_type = getattr(row, "custom_ndis_service_type", None)
        funding_source = getattr(row, "custom_ndis_funding_source", None) or getattr(
            doc, "custom_ndis_funding_source", None
        )
        support_category = get_support_category(support_item)

        if budget_mode != "Disabled":
            budget_result = validate_budget_row(
                doc=doc,
                row=row,
                row_amount=row_amount,
                participant=participant,
                service_date=service_date,
                support_item=support_item,
                service_type=service_type,
                support_category=support_category,
                funding_source=funding_source,
                current_usage_map=budget_current_usage,
            )

            if budget_result.get("message"):
                if budget_result.get("block") and budget_mode == "Warn and Block":
                    blockers.append(budget_result["message"])
                else:
                    warnings.append(budget_result["message"])

        else:
            set_row_field(row, "custom_ndis_budget_check_status", "Disabled")

        if booking_mode != "Disabled":
            booking_result = validate_booking_row(
                doc=doc,
                row=row,
                row_amount=row_amount,
                participant=participant,
                service_date=service_date,
                support_item=support_item,
                service_type=service_type,
                support_category=support_category,
                funding_source=funding_source,
                current_usage_map=booking_current_usage,
            )

            if booking_result.get("message"):
                if booking_result.get("block") and booking_mode == "Warn and Block":
                    blockers.append(booking_result["message"])
                else:
                    warnings.append(booking_result["message"])

        else:
            set_row_field(row, "custom_ndis_service_booking_check_status", "Disabled")

    set_doc_field(doc, "custom_ndis_validation_last_run", now_datetime())

    if blockers:
        set_doc_field(doc, "custom_ndis_validation_status", "Blocked")
        frappe.throw(
            _("NDIS budget/service booking validation blocked this invoice:<br><br>{0}").format(
                "<br>".join(blockers)
            )
        )

    if warnings:
        set_doc_field(doc, "custom_ndis_validation_status", "Passed With Warnings")
        frappe.msgprint(
            _("NDIS budget/service booking warnings:<br><br>{0}").format(
                "<br>".join(warnings)
            ),
            indicator="orange",
            alert=True,
        )
    else:
        set_doc_field(doc, "custom_ndis_validation_status", "Passed")


def validate_budget_row(
    doc,
    row,
    row_amount,
    participant,
    service_date,
    support_item,
    service_type,
    support_category,
    funding_source,
    current_usage_map,
):
    budget = find_matching_budget(
        participant=participant,
        service_date=service_date,
        support_item=support_item,
        service_type=service_type,
        support_category=support_category,
        funding_source=funding_source,
    )

    if not budget:
        set_row_field(row, "custom_ndis_plan_budget", None)
        set_row_field(row, "custom_ndis_budget_check_status", "No Budget Found")
        set_row_field(row, "custom_ndis_budget_validation_note", "No active matching NDIS Plan Budget found.")

        return {
            "block": True,
            "message": f"Row {row.idx}: No active NDIS Plan Budget found for participant {participant}.",
        }

    set_row_field(row, "custom_ndis_plan_budget", budget.name)

    used_before_invoice = calculate_used_for_budget(budget, exclude_invoice=doc.name)
    used_inside_invoice_before = flt(current_usage_map.get(budget.name))
    remaining_before = flt(budget.budget_amount) - used_before_invoice - used_inside_invoice_before
    remaining_after = remaining_before - row_amount

    current_usage_map[budget.name] = used_inside_invoice_before + row_amount

    set_row_field(row, "custom_ndis_budget_remaining_before", remaining_before)
    set_row_field(row, "custom_ndis_budget_remaining_after", remaining_after)

    if remaining_after < 0:
        set_row_field(row, "custom_ndis_budget_check_status", "Over Budget")
        set_row_field(
            row,
            "custom_ndis_budget_validation_note",
            f"Budget exceeded by {abs(remaining_after):.2f}.",
        )

        return {
            "block": True,
            "message": (
                f"Row {row.idx}: Budget {budget.name} will be exceeded. "
                f"Remaining before row: {remaining_before:.2f}, row amount: {row_amount:.2f}."
            ),
        }

    set_row_field(row, "custom_ndis_budget_check_status", "Within Budget")

    warning_threshold = flt(budget.get("warning_threshold_percent") or 80)
    budget_amount = flt(budget.budget_amount)

    if budget_amount > 0:
        used_after = budget_amount - remaining_after
        used_percent = (used_after / budget_amount) * 100

        if used_percent >= warning_threshold:
            set_row_field(
                row,
                "custom_ndis_budget_validation_note",
                f"Budget usage will reach {used_percent:.2f}% after this row.",
            )

            return {
                "block": False,
                "message": (
                    f"Row {row.idx}: Budget {budget.name} usage will reach "
                    f"{used_percent:.2f}% after this invoice line."
                ),
            }

    set_row_field(row, "custom_ndis_budget_validation_note", "Budget check passed.")
    return {"block": False, "message": None}


def validate_booking_row(
    doc,
    row,
    row_amount,
    participant,
    service_date,
    support_item,
    service_type,
    support_category,
    funding_source,
    current_usage_map,
):
    booking = find_matching_booking(
        participant=participant,
        service_date=service_date,
        support_item=support_item,
        service_type=service_type,
        support_category=support_category,
        funding_source=funding_source,
    )

    if not booking:
        set_row_field(row, "custom_ndis_service_booking", None)
        set_row_field(row, "custom_ndis_service_booking_check_status", "No Booking Found")

        existing_note = getattr(row, "custom_ndis_budget_validation_note", None) or ""
        set_row_field(
            row,
            "custom_ndis_budget_validation_note",
            (existing_note + " No active matching service booking/internal funding authority found.").strip(),
        )

        return {
            "block": True,
            "message": f"Row {row.idx}: No active NDIS Service Booking found for participant {participant}.",
        }

    set_row_field(row, "custom_ndis_service_booking", booking.name)

    used_before_invoice = calculate_used_for_booking(booking, exclude_invoice=doc.name)
    used_inside_invoice_before = flt(current_usage_map.get(booking.name))
    remaining_before = flt(booking.booking_amount) - used_before_invoice - used_inside_invoice_before
    remaining_after = remaining_before - row_amount

    current_usage_map[booking.name] = used_inside_invoice_before + row_amount

    set_row_field(row, "custom_ndis_booking_remaining_before", remaining_before)
    set_row_field(row, "custom_ndis_booking_remaining_after", remaining_after)

    if remaining_after < 0:
        set_row_field(row, "custom_ndis_service_booking_check_status", "Over Booking")

        existing_note = getattr(row, "custom_ndis_budget_validation_note", None) or ""
        set_row_field(
            row,
            "custom_ndis_budget_validation_note",
            (existing_note + f" Booking exceeded by {abs(remaining_after):.2f}.").strip(),
        )

        return {
            "block": True,
            "message": (
                f"Row {row.idx}: Service Booking {booking.name} will be exceeded. "
                f"Remaining before row: {remaining_before:.2f}, row amount: {row_amount:.2f}."
            ),
        }

    set_row_field(row, "custom_ndis_service_booking_check_status", "Within Booking")
    return {"block": False, "message": None}


def find_matching_budget(
    participant,
    service_date,
    support_item=None,
    service_type=None,
    support_category=None,
    funding_source=None,
):
    if not participant or not service_date:
        return None

    service_date = getdate(service_date)

    budgets = frappe.get_all(
        "NDIS Plan Budget",
        filters={
            "participant": participant,
            "status": ["in", ["Active"]],
        },
        fields=[
            "name",
            "participant",
            "funding_source",
            "support_category",
            "service_type",
            "support_item",
            "plan_start_date",
            "plan_end_date",
            "budget_amount",
            "claimed_amount",
            "remaining_budget",
            "status",
            "budget_control_level",
            "budget_control_mode",
            "warning_threshold_percent",
        ],
        order_by="modified desc",
    )

    best = None
    best_score = -1

    for budget in budgets:
        if budget.plan_start_date and service_date < getdate(budget.plan_start_date):
            continue

        if budget.plan_end_date and service_date > getdate(budget.plan_end_date):
            continue

        score = score_budget_match(
            budget=budget,
            support_item=support_item,
            service_type=service_type,
            support_category=support_category,
            funding_source=funding_source,
        )

        if score > best_score:
            best_score = score
            best = budget

    return best


def find_matching_booking(
    participant,
    service_date,
    support_item=None,
    service_type=None,
    support_category=None,
    funding_source=None,
):
    if not participant or not service_date:
        return None

    service_date = getdate(service_date)

    bookings = frappe.get_all(
        "NDIS Service Booking",
        filters={
            "participant": participant,
            "status": ["in", ["Active"]],
        },
        fields=[
            "name",
            "participant",
            "funding_source",
            "support_category",
            "service_type",
            "support_item",
            "start_date",
            "end_date",
            "booking_amount",
            "used_amount",
            "remaining_amount",
            "status",
            "booking_control_mode",
        ],
        order_by="modified desc",
    )

    best = None
    best_score = -1

    for booking in bookings:
        if booking.start_date and service_date < getdate(booking.start_date):
            continue

        if booking.end_date and service_date > getdate(booking.end_date):
            continue

        score = score_booking_match(
            booking=booking,
            support_item=support_item,
            service_type=service_type,
            support_category=support_category,
            funding_source=funding_source,
        )

        if score > best_score:
            best_score = score
            best = booking

    return best


def score_budget_match(budget, support_item=None, service_type=None, support_category=None, funding_source=None):
    score = 0

    if budget.funding_source:
        if funding_source and budget.funding_source == funding_source:
            score += 10
        else:
            return -1

    control_level = budget.budget_control_level or infer_control_level(budget)

    if control_level == "Support Item":
        if budget.support_item:
            if support_item and budget.support_item == support_item:
                return score + 100
            return -1

    if control_level == "Service Type":
        if budget.service_type:
            if service_type and budget.service_type == service_type:
                return score + 50
            return -1

    if control_level == "Support Category":
        if budget.support_category:
            if support_category and budget.support_category == support_category:
                return score + 20
            return -1

    if control_level == "Participant Total":
        return score + 1

    return score + score_optional_dimension_match(
        record=budget,
        support_item=support_item,
        service_type=service_type,
        support_category=support_category,
    )


def score_booking_match(booking, support_item=None, service_type=None, support_category=None, funding_source=None):
    score = 0

    if booking.funding_source:
        if funding_source and booking.funding_source == funding_source:
            score += 10
        else:
            return -1

    return score + score_optional_dimension_match(
        record=booking,
        support_item=support_item,
        service_type=service_type,
        support_category=support_category,
    )


def infer_control_level(record):
    if record.support_item:
        return "Support Item"
    if record.service_type:
        return "Service Type"
    if record.support_category:
        return "Support Category"
    return "Participant Total"


def score_optional_dimension_match(record, support_item=None, service_type=None, support_category=None):
    if record.support_item:
        if support_item and record.support_item == support_item:
            return 100
        return -1

    if record.service_type:
        if service_type and record.service_type == service_type:
            return 50
        return -1

    if record.support_category:
        if support_category and record.support_category == support_category:
            return 20
        return -1

    return 1


def calculate_used_for_budget(budget, exclude_invoice=None):
    conditions = [
        "si.docstatus = 1",
        "ifnull(sii.custom_ndis_claimable, 0) = 1",
        "sii.custom_ndis_participant = %(participant)s",
    ]

    params = {
        "participant": budget.participant,
    }

    if exclude_invoice:
        conditions.append("si.name != %(exclude_invoice)s")
        params["exclude_invoice"] = exclude_invoice

    if budget.plan_start_date:
        conditions.append("sii.custom_ndis_service_date >= %(plan_start_date)s")
        params["plan_start_date"] = budget.plan_start_date

    if budget.plan_end_date:
        conditions.append("sii.custom_ndis_service_date <= %(plan_end_date)s")
        params["plan_end_date"] = budget.plan_end_date

    if budget.funding_source:
        conditions.append("sii.custom_ndis_funding_source = %(funding_source)s")
        params["funding_source"] = budget.funding_source

    if budget.support_item:
        conditions.append("sii.custom_ndis_support_item = %(support_item)s")
        params["support_item"] = budget.support_item

    if budget.service_type:
        conditions.append("sii.custom_ndis_service_type = %(service_type)s")
        params["service_type"] = budget.service_type

    if budget.support_category and not budget.support_item:
        conditions.append("nsi.support_category = %(support_category)s")
        params["support_category"] = budget.support_category

    result = frappe.db.sql(
        f"""
        SELECT COALESCE(SUM(COALESCE(sii.net_amount, sii.amount, 0)), 0) AS used_amount
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
        LEFT JOIN `tabNDIS Support Item` nsi ON nsi.name = sii.custom_ndis_support_item
        WHERE {" AND ".join(conditions)}
        """,
        params,
        as_dict=True,
    )

    return flt(result[0].used_amount if result else 0)


def calculate_used_for_booking(booking, exclude_invoice=None):
    conditions = [
        "si.docstatus = 1",
        "ifnull(sii.custom_ndis_claimable, 0) = 1",
        "sii.custom_ndis_participant = %(participant)s",
    ]

    params = {
        "participant": booking.participant,
    }

    if exclude_invoice:
        conditions.append("si.name != %(exclude_invoice)s")
        params["exclude_invoice"] = exclude_invoice

    if booking.start_date:
        conditions.append("sii.custom_ndis_service_date >= %(start_date)s")
        params["start_date"] = booking.start_date

    if booking.end_date:
        conditions.append("sii.custom_ndis_service_date <= %(end_date)s")
        params["end_date"] = booking.end_date

    if booking.funding_source:
        conditions.append("sii.custom_ndis_funding_source = %(funding_source)s")
        params["funding_source"] = booking.funding_source

    if booking.support_item:
        conditions.append("sii.custom_ndis_support_item = %(support_item)s")
        params["support_item"] = booking.support_item

    if booking.service_type:
        conditions.append("sii.custom_ndis_service_type = %(service_type)s")
        params["service_type"] = booking.service_type

    if booking.support_category and not booking.support_item:
        conditions.append("nsi.support_category = %(support_category)s")
        params["support_category"] = booking.support_category

    result = frappe.db.sql(
        f"""
        SELECT COALESCE(SUM(COALESCE(sii.net_amount, sii.amount, 0)), 0) AS used_amount
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
        LEFT JOIN `tabNDIS Support Item` nsi ON nsi.name = sii.custom_ndis_support_item
        WHERE {" AND ".join(conditions)}
        """,
        params,
        as_dict=True,
    )

    return flt(result[0].used_amount if result else 0)


def update_usage_from_sales_invoice(doc, method=None):
    """
    Runs on submit and cancel.
    Recalculates affected budgets/bookings from submitted invoices only.
    """

    if not getattr(doc, "custom_is_ndis_invoice", 0):
        return

    affected_budgets = set()
    affected_bookings = set()

    for row in doc.items:
        if not getattr(row, "custom_ndis_claimable", 0):
            continue

        linked_budget = getattr(row, "custom_ndis_plan_budget", None)
        if linked_budget and frappe.db.exists("NDIS Plan Budget", linked_budget):
            affected_budgets.add(linked_budget)
        else:
            budget = find_matching_budget_for_row(doc, row)
            if budget:
                affected_budgets.add(budget.name)

        linked_booking = getattr(row, "custom_ndis_service_booking", None)
        if linked_booking and frappe.db.exists("NDIS Service Booking", linked_booking):
            affected_bookings.add(linked_booking)
        else:
            booking = find_matching_booking_for_row(doc, row)
            if booking:
                affected_bookings.add(booking.name)

    for budget_name in affected_budgets:
        recalculate_budget_usage(budget_name)

    for booking_name in affected_bookings:
        recalculate_booking_usage(booking_name)


def find_matching_budget_for_row(doc, row):
    participant = getattr(row, "custom_ndis_participant", None) or doc.customer
    service_date = getattr(row, "custom_ndis_service_date", None)
    support_item = getattr(row, "custom_ndis_support_item", None)
    service_type = getattr(row, "custom_ndis_service_type", None)
    funding_source = getattr(row, "custom_ndis_funding_source", None) or getattr(
        doc, "custom_ndis_funding_source", None
    )
    support_category = get_support_category(support_item)

    return find_matching_budget(
        participant=participant,
        service_date=service_date,
        support_item=support_item,
        service_type=service_type,
        support_category=support_category,
        funding_source=funding_source,
    )


def find_matching_booking_for_row(doc, row):
    participant = getattr(row, "custom_ndis_participant", None) or doc.customer
    service_date = getattr(row, "custom_ndis_service_date", None)
    support_item = getattr(row, "custom_ndis_support_item", None)
    service_type = getattr(row, "custom_ndis_service_type", None)
    funding_source = getattr(row, "custom_ndis_funding_source", None) or getattr(
        doc, "custom_ndis_funding_source", None
    )
    support_category = get_support_category(support_item)

    return find_matching_booking(
        participant=participant,
        service_date=service_date,
        support_item=support_item,
        service_type=service_type,
        support_category=support_category,
        funding_source=funding_source,
    )


@frappe.whitelist()
def recalculate_budget_usage(budget_name):
    assert_action("manage_budget")

    budget = frappe.get_doc("NDIS Plan Budget", budget_name)

    used = calculate_used_for_budget(budget)
    remaining = flt(budget.budget_amount) - used

    new_status = budget.status
    today_date = getdate(today())

    if budget.status != "Closed":
        if budget.plan_end_date and getdate(budget.plan_end_date) < today_date:
            new_status = "Expired"
        elif flt(budget.budget_amount) > 0 and remaining <= 0:
            new_status = "Exhausted"
        elif budget.status in ["Draft", "Exhausted", "Expired"] and remaining > 0:
            new_status = "Active"

    frappe.db.set_value(
        "NDIS Plan Budget",
        budget.name,
        {
            "claimed_amount": used,
            "remaining_budget": remaining,
            "status": new_status,
            "last_recalculated_on": now_datetime(),
        },
    )

    return {
        "budget": budget.name,
        "budget_amount": flt(budget.budget_amount),
        "claimed_amount": used,
        "remaining_budget": remaining,
        "status": new_status,
    }


@frappe.whitelist()
def recalculate_booking_usage(booking_name):
    assert_action("manage_budget")

    booking = frappe.get_doc("NDIS Service Booking", booking_name)

    used = calculate_used_for_booking(booking)
    remaining = flt(booking.booking_amount) - used

    new_status = booking.status
    today_date = getdate(today())

    if booking.status != "Closed":
        if booking.end_date and getdate(booking.end_date) < today_date:
            new_status = "Expired"
        elif flt(booking.booking_amount) > 0 and remaining <= 0:
            new_status = "Exhausted"
        elif booking.status in ["Expired", "Exhausted"] and remaining > 0:
            new_status = "Active"

    frappe.db.set_value(
        "NDIS Service Booking",
        booking.name,
        {
            "used_amount": used,
            "remaining_amount": remaining,
            "status": new_status,
            "last_recalculated_on": now_datetime(),
        },
    )

    return {
        "service_booking": booking.name,
        "booking_amount": flt(booking.booking_amount),
        "used_amount": used,
        "remaining_amount": remaining,
        "status": new_status,
    }


@frappe.whitelist()
def recalculate_all_active_budgets_and_bookings():
    assert_action("manage_budget")

    budgets = frappe.get_all(
        "NDIS Plan Budget",
        filters={"status": ["in", ["Active", "Exhausted", "Expired", "Draft"]]},
        pluck="name",
    )

    bookings = frappe.get_all(
        "NDIS Service Booking",
        filters={"status": ["in", ["Active", "Exhausted", "Expired"]]},
        pluck="name",
    )

    budget_results = [recalculate_budget_usage(name) for name in budgets]
    booking_results = [recalculate_booking_usage(name) for name in bookings]

    frappe.db.commit()

    return {
        "budgets_recalculated": len(budget_results),
        "bookings_recalculated": len(booking_results),
        "budget_preview": budget_results[:10],
        "booking_preview": booking_results[:10],
    }


def get_support_category(support_item):
    if not support_item:
        return None

    return frappe.db.get_value("NDIS Support Item", support_item, "support_category")


def get_row_amount(row):
    amount = flt(getattr(row, "net_amount", None) or getattr(row, "amount", None) or 0)

    if amount:
        return amount

    return flt(getattr(row, "qty", 0)) * flt(getattr(row, "rate", 0))


def set_row_field(row, fieldname, value):
    if row.meta.has_field(fieldname):
        setattr(row, fieldname, value)


def set_doc_field(doc, fieldname, value):
    if doc.meta.has_field(fieldname):
        setattr(doc, fieldname, value)


def mark_disabled(doc):
    for row in doc.items:
        set_row_field(row, "custom_ndis_budget_check_status", "Disabled")
        set_row_field(row, "custom_ndis_service_booking_check_status", "Disabled")
