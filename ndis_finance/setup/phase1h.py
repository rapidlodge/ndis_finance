import json

import frappe
from frappe import _

from ndis_finance.setup.install import MODULE


WORKSPACE_NAME = "NDIS Finance"

OPEN_RECOVERY_STATUSES = ["Open", "In Follow Up", "Waiting For Response", "Escalated"]

NUMBER_CARDS = [
    {
        "label": "Open Recovery Cases",
        "doctype": "NDIS Recovery Case",
        "function": "Count",
        "filters": [
            ["NDIS Recovery Case", "status", "in", OPEN_RECOVERY_STATUSES],
        ],
    },
    {
        "label": "Overdue Follow Ups",
        "doctype": "NDIS Recovery Case",
        "function": "Count",
        "filters": [
            ["NDIS Recovery Case", "status", "in", OPEN_RECOVERY_STATUSES],
            ["NDIS Recovery Case", "next_follow_up_date", "<=", "Today"],
        ],
    },
    {
        "label": "Open Leakage Records",
        "doctype": "NDIS Funding Leakage Register",
        "function": "Count",
        "filters": [
            ["NDIS Funding Leakage Register", "status", "in", ["Open", "In Review"]],
        ],
    },
    {
        "label": "Open Leakage Amount",
        "doctype": "NDIS Funding Leakage Register",
        "function": "Sum",
        "aggregate_field": "variance_amount",
        "filters": [
            ["NDIS Funding Leakage Register", "status", "in", ["Open", "In Review"]],
        ],
    },
    {
        "label": "Claim Exception Amount",
        "doctype": "NDIS Claim Line",
        "function": "Sum",
        "aggregate_field": "shortfall_amount",
        "filters": [
            ["NDIS Claim Line", "claim_status", "in", ["Short Paid", "Rejected", "Reclaim Required"]],
        ],
    },
    {
        "label": "Rejected Claims",
        "doctype": "NDIS Claim Line",
        "function": "Count",
        "filters": [
            ["NDIS Claim Line", "claim_status", "=", "Rejected"],
        ],
    },
]

REPORT_SHORTCUTS = [
    {
        "label": "CFO Exception Dashboard",
        "type": "Report",
        "link_to": "NDIS CFO Exception Dashboard",
        "ref_doctype": "NDIS Recovery Case",
    },
    {
        "label": "Recovery Ageing",
        "type": "Report",
        "link_to": "NDIS Recovery Ageing Report",
        "ref_doctype": "NDIS Recovery Case",
    },
    {
        "label": "Claim Exceptions",
        "type": "Report",
        "link_to": "NDIS Claim Exception Report",
        "ref_doctype": "NDIS Claim Line",
    },
    {
        "label": "Funding Leakage",
        "type": "Report",
        "link_to": "NDIS Funding Leakage Report",
        "ref_doctype": "NDIS Funding Leakage Register",
    },
]

DOCTYPE_SHORTCUTS = [
    {"label": "Claim Batches", "type": "DocType", "link_to": "NDIS Claim Batch"},
    {"label": "Claim Lines", "type": "DocType", "link_to": "NDIS Claim Line"},
    {
        "label": "Payment Reconciliation",
        "type": "DocType",
        "link_to": "NDIS Payment Reconciliation Batch",
    },
    {"label": "Recovery Cases", "type": "DocType", "link_to": "NDIS Recovery Case"},
    {
        "label": "Funding Leakage Register",
        "type": "DocType",
        "link_to": "NDIS Funding Leakage Register",
    },
    {
        "label": "Participant Financial Profiles",
        "type": "DocType",
        "link_to": "NDIS Participant Financial Profile",
    },
    {"label": "Plan Budgets", "type": "DocType", "link_to": "NDIS Plan Budget"},
    {"label": "Service Bookings", "type": "DocType", "link_to": "NDIS Service Booking"},
    {"label": "Support Catalogue", "type": "DocType", "link_to": "NDIS Support Item"},
    {"label": "Sales Invoices", "type": "DocType", "link_to": "Sales Invoice"},
    {"label": "Customers / Participants", "type": "DocType", "link_to": "Customer"},
]

SHORTCUTS = REPORT_SHORTCUTS + DOCTYPE_SHORTCUTS

WORKSPACE_ROLES = [
    "System Manager",
    "NDIS CFO",
    "NDIS Finance Manager",
    "NDIS Finance Officer",
    "NDIS Billing Officer",
    "NDIS Claims Officer",
    "NDIS Recovery Officer",
    "NDIS Finance Read Only",
]


@frappe.whitelist()
def install():
    validate_phase1g()
    create_number_cards()
    create_workspace()
    frappe.db.commit()
    return health_check()


def validate_phase1g():
    required_doctypes = [
        "Workspace",
        "Number Card",
        "Report",
        "NDIS Recovery Case",
        "NDIS Funding Leakage Register",
        "NDIS Claim Line",
        "NDIS Claim Batch",
        "NDIS Payment Reconciliation Batch",
        "NDIS Participant Financial Profile",
        "NDIS Plan Budget",
        "NDIS Service Booking",
        "NDIS Support Item",
        "Sales Invoice",
        "Customer",
    ]

    missing = [dt for dt in required_doctypes if not frappe.db.exists("DocType", dt)]

    if missing:
        frappe.throw(
            _("Phase 1H requires previous phases. Missing DocTypes: {0}").format(
                ", ".join(missing)
            )
        )

    required_reports = [shortcut["link_to"] for shortcut in REPORT_SHORTCUTS]
    missing_reports = [report for report in required_reports if not frappe.db.exists("Report", report)]

    if missing_reports:
        frappe.throw(
            _("Phase 1H requires Phase 1G reports. Missing Reports: {0}").format(
                ", ".join(missing_reports)
            )
        )


def set_if_exists(doc, fieldname, value):
    if doc.meta.has_field(fieldname):
        setattr(doc, fieldname, value)


def set_child_value(row, fieldname, value):
    if value is None:
        return

    if row.meta.has_field(fieldname):
        setattr(row, fieldname, value)


def create_number_cards():
    for card in NUMBER_CARDS:
        ensure_number_card(card)


def ensure_number_card(card):
    existing = get_number_card_name(card)

    if existing:
        doc = frappe.get_doc("Number Card", existing)
    else:
        doc = frappe.new_doc("Number Card")
        doc.name = card["label"]
        doc.flags.name_set = True

    set_if_exists(doc, "label", card["label"])
    set_if_exists(doc, "module", MODULE)
    set_if_exists(doc, "type", "Document Type")
    set_if_exists(doc, "document_type", card["doctype"])
    set_if_exists(doc, "reference_document", card["doctype"])
    set_if_exists(doc, "doctype_name", card["doctype"])
    set_if_exists(doc, "function", card["function"])
    set_if_exists(doc, "aggregate_function", card["function"])
    set_if_exists(doc, "is_public", 1)
    set_if_exists(doc, "is_standard", 1)
    set_if_exists(doc, "show_percentage_stats", 0)
    set_if_exists(doc, "show_full_number", 1)

    aggregate_field = card.get("aggregate_field")
    if aggregate_field:
        for fieldname in [
            "aggregate_function_based_on",
            "aggregate_field",
            "result_field",
            "fieldname",
            "field_to_compute",
        ]:
            set_if_exists(doc, fieldname, aggregate_field)
    else:
        set_if_exists(doc, "aggregate_function_based_on", None)

    filters_json = json.dumps(card.get("filters") or [])
    for fieldname in ["filters_json", "filters", "filter_json"]:
        set_if_exists(doc, fieldname, filters_json)

    if card["function"] == "Sum":
        set_if_exists(doc, "currency", frappe.defaults.get_global_default("currency") or "AUD")

    doc.save(ignore_permissions=True)


def get_number_card_name(card):
    return frappe.db.exists("Number Card", card["label"]) or frappe.db.exists(
        "Number Card",
        {"label": card["label"]},
    )


def block_id(label):
    return "".join(
        character if character.isalnum() or character == "_" else "_"
        for character in frappe.scrub(label)
    ).strip("_")


def create_workspace():
    existing = frappe.db.exists("Workspace", WORKSPACE_NAME) or frappe.db.exists(
        "Workspace",
        {"label": WORKSPACE_NAME},
    )

    if existing:
        doc = frappe.get_doc("Workspace", existing)
    else:
        doc = frappe.new_doc("Workspace")
        doc.name = WORKSPACE_NAME
        doc.flags.name_set = True

    set_if_exists(doc, "label", WORKSPACE_NAME)
    set_if_exists(doc, "title", WORKSPACE_NAME)
    set_if_exists(doc, "module", MODULE)
    set_if_exists(doc, "app", "ndis_finance")
    set_if_exists(doc, "type", "Workspace")
    set_if_exists(doc, "icon", "accounting")
    set_if_exists(doc, "indicator_color", "blue")
    set_if_exists(doc, "public", 1)
    set_if_exists(doc, "is_hidden", 0)
    set_if_exists(doc, "hide_custom", 0)
    set_if_exists(doc, "for_user", "")

    clear_workspace_children(doc)
    append_workspace_number_cards(doc)
    append_workspace_shortcuts(doc)
    append_workspace_links(doc)
    append_workspace_roles(doc)

    set_if_exists(doc, "content", json.dumps(build_workspace_content()))

    doc.save(ignore_permissions=True)


def clear_workspace_children(doc):
    for fieldname in ["number_cards", "shortcuts", "links", "quick_lists", "charts", "custom_blocks"]:
        if doc.meta.has_field(fieldname):
            setattr(doc, fieldname, [])


def append_workspace_number_cards(doc):
    if not doc.meta.has_field("number_cards"):
        return

    for card in NUMBER_CARDS:
        row = doc.append("number_cards", {})
        set_child_value(row, "number_card_name", get_number_card_name(card) or card["label"])
        set_child_value(row, "label", card["label"])


def append_workspace_shortcuts(doc):
    if not doc.meta.has_field("shortcuts"):
        return

    for shortcut in SHORTCUTS:
        row = doc.append("shortcuts", {})
        set_child_value(row, "type", shortcut["type"])
        set_child_value(row, "link_to", shortcut["link_to"])
        set_child_value(row, "label", shortcut["label"])
        set_child_value(row, "doc_view", "List" if shortcut["type"] == "DocType" else None)
        set_child_value(row, "report_ref_doctype", shortcut.get("ref_doctype"))
        set_child_value(row, "stats_filter", "[]")
        set_child_value(row, "color", "Grey")


def append_workspace_links(doc):
    if not doc.meta.has_field("links"):
        return

    append_card_break(doc, "Reports and Exceptions")
    for shortcut in REPORT_SHORTCUTS:
        append_workspace_link(doc, shortcut)

    append_card_break(doc, "Claims and Reconciliation")
    for shortcut in DOCTYPE_SHORTCUTS[:5]:
        append_workspace_link(doc, shortcut)

    append_card_break(doc, "Budgets, Catalogue and Billing")
    for shortcut in DOCTYPE_SHORTCUTS[5:]:
        append_workspace_link(doc, shortcut)


def append_card_break(doc, label):
    row = doc.append("links", {})
    set_child_value(row, "type", "Card Break")
    set_child_value(row, "label", label)


def append_workspace_link(doc, shortcut):
    row = doc.append("links", {})
    set_child_value(row, "type", "Link")
    set_child_value(row, "label", shortcut["label"])
    set_child_value(row, "link_type", shortcut["type"])
    set_child_value(row, "link_to", shortcut["link_to"])
    set_child_value(row, "report_ref_doctype", shortcut.get("ref_doctype"))
    set_child_value(row, "is_query_report", 0)


def append_workspace_roles(doc):
    if not doc.meta.has_field("roles"):
        return

    doc.roles = []
    for role in WORKSPACE_ROLES:
        if frappe.db.exists("Role", role):
            doc.append("roles", {"role": role})


def build_workspace_content():
    blocks = [
        {
            "id": "ndis_finance_heading",
            "type": "header",
            "data": {
                "text": '<span class="h4"><b>NDIS Finance Control Centre</b></span>',
                "col": 12,
            },
        },
        {
            "id": "ndis_finance_summary",
            "type": "paragraph",
            "data": {
                "text": "CFO-level NDIS finance controls for claims, payments, leakage, recovery, budgets and service bookings.",
                "col": 12,
            },
        },
    ]

    for card in NUMBER_CARDS:
        blocks.append(
            {
                "id": block_id(card["label"]),
                "type": "number_card",
                "data": {
                    "number_card_name": get_number_card_name(card) or card["label"],
                    "col": 2,
                },
            }
        )

    blocks.append(
        {
            "id": "ndis_finance_reports_heading",
            "type": "header",
            "data": {
                "text": '<span class="h4"><b>Reports and Exceptions</b></span>',
                "col": 12,
            },
        }
    )

    for shortcut in SHORTCUTS:
        blocks.append(
            {
                "id": block_id(shortcut["label"]),
                "type": "shortcut",
                "data": {
                    "shortcut_name": shortcut["label"],
                    "col": 3,
                },
            }
        )

    return blocks


@frappe.whitelist()
def health_check():
    cards = {
        card["label"]: bool(get_number_card_name(card))
        for card in NUMBER_CARDS
    }

    workspace_name = frappe.db.exists("Workspace", WORKSPACE_NAME) or frappe.db.exists(
        "Workspace",
        {"label": WORKSPACE_NAME},
    )

    reports = {
        shortcut["link_to"]: bool(frappe.db.exists("Report", shortcut["link_to"]))
        for shortcut in REPORT_SHORTCUTS
    }

    doctypes = {
        shortcut["link_to"]: bool(frappe.db.exists("DocType", shortcut["link_to"]))
        for shortcut in DOCTYPE_SHORTCUTS
    }

    workspace_detail = {}
    if workspace_name:
        workspace = frappe.get_doc("Workspace", workspace_name)
        workspace_detail = {
            "name": workspace.name,
            "label": getattr(workspace, "label", None),
            "module": getattr(workspace, "module", None),
            "public": getattr(workspace, "public", None),
            "is_hidden": getattr(workspace, "is_hidden", None),
            "has_content": bool(getattr(workspace, "content", None)),
            "number_card_rows": len(getattr(workspace, "number_cards", []) or []),
            "shortcut_rows": len(getattr(workspace, "shortcuts", []) or []),
            "link_rows": len(getattr(workspace, "links", []) or []),
        }

    return {
        "workspace": {
            WORKSPACE_NAME: bool(workspace_name),
            "detail": workspace_detail,
        },
        "number_cards": cards,
        "report_shortcuts": reports,
        "doctype_shortcuts": doctypes,
    }
