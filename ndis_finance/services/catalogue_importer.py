import csv
import os
import re

import frappe
from frappe import _
from frappe.utils import now_datetime
from frappe.utils.file_manager import get_file_path

from ndis_finance.services.permissions import assert_action


TEXT_ALIASES = {
    "support_item_number": [
        "support item number",
        "support item no",
        "support item",
        "item number",
        "supportitemnumber",
        "item",
    ],
    "support_item_name": [
        "support item name",
        "support item description",
        "item name",
        "description",
        "support name",
        "supportitemname",
    ],
    "support_category": [
        "support category",
        "support category name",
        "category",
        "category name",
        "supportcategory",
    ],
    "registration_group": [
        "registration group",
        "registration group name",
        "registration group number",
        "registrationgroup",
    ],
    "unit": [
        "unit",
        "unit of measure",
        "uom",
        "claim type",
    ],
    "price_limit": [
        "price limit",
        "maximum price",
        "max price",
        "national price",
        "national",
        "price",
        "amount",
    ],
    "price_national": [
        "national",
        "national price",
        "national price limit",
        "price national",
    ],
    "price_nsw": ["nsw", "new south wales"],
    "price_vic": ["vic", "victoria"],
    "price_qld": ["qld", "queensland"],
    "price_sa": ["sa", "south australia"],
    "price_wa": ["wa", "western australia"],
    "price_tas": ["tas", "tasmania"],
    "price_act": ["act", "australian capital territory"],
    "price_nt": ["nt", "northern territory"],
    "price_remote": ["remote", "remote price", "remote price limit"],
    "price_very_remote": [
        "very remote",
        "very remote price",
        "very remote price limit",
        "veryremote",
    ],
    "quote_required": ["quote required", "quote", "quoterequired"],
    "provider_travel_allowed": [
        "provider travel",
        "provider travel allowed",
        "travel",
    ],
    "non_face_to_face_allowed": [
        "non face to face",
        "non-face-to-face",
        "non face-to-face",
        "nf2f",
    ],
    "cancellation_allowed": [
        "cancellation",
        "short notice cancellation",
        "short notice cancellations",
    ],
    "ndia_requested_reports_allowed": [
        "ndia requested reports",
        "reports",
        "requested reports",
    ],
    "irregular_sil_allowed": [
        "irregular sil",
        "irregular sil supports",
    ],
    "gst_treatment": [
        "gst",
        "gst treatment",
        "tax treatment",
    ],
}


def normalise_key(value):
    value = str(value or "").strip().lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def normalise_compact(value):
    return re.sub(r"[^a-z0-9]+", "", normalise_key(value))


def clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


def clean_money(value):
    if value is None:
        return 0

    if isinstance(value, (int, float)):
        return float(value or 0)

    text = str(value).strip()
    if not text:
        return 0

    if text.lower() in ["-", "n/a", "na", "nil", "not applicable"]:
        return 0

    text = text.replace("$", "").replace(",", "").strip()

    match = re.search(r"-?\d+(\.\d+)?", text)
    if not match:
        return 0

    return float(match.group(0))


def clean_bool(value):
    if value is None:
        return 0

    if isinstance(value, bool):
        return 1 if value else 0

    text = str(value).strip().lower()

    if text in ["1", "yes", "y", "true", "allowed", "available", "x"]:
        return 1

    if "yes" in text or "allowed" in text:
        return 1

    return 0


def clean_gst_treatment(value):
    text = normalise_key(value)

    if not text:
        return "To Review"

    if "gst free" in text or "gstfree" in normalise_compact(value):
        return "GST Free"

    if "taxable" in text or "gst applies" in text:
        return "Taxable"

    if "input taxed" in text:
        return "Input Taxed"

    if "out of scope" in text:
        return "Out of Scope"

    return "To Review"


def get_physical_file_path(file_path=None, file_url=None, file_docname=None):
    if file_path:
        return file_path

    if file_docname:
        file_url = frappe.db.get_value("File", file_docname, "file_url")

    if file_url:
        return get_file_path(file_url)

    frappe.throw(_("Please provide file_path, file_url, or file_docname."))


def load_rows_from_file(path):
    ext = os.path.splitext(path)[1].lower()

    if ext in [".xlsx", ".xlsm"]:
        return load_rows_from_xlsx(path)

    if ext == ".csv":
        return load_rows_from_csv(path)

    frappe.throw(_("Unsupported file type: {0}. Please use XLSX or CSV.").format(ext))


def load_rows_from_xlsx(path):
    try:
        import openpyxl
    except ImportError:
        frappe.throw(
            _("openpyxl is required to import XLSX files. Install it in the bench environment.")
        )

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)

    best_rows = []
    best_score = -1

    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        score = score_rows_for_catalogue(rows)

        if score > best_score:
            best_score = score
            best_rows = rows

    return rows_to_dicts(best_rows)


def load_rows_from_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows = list(reader)

    return rows_to_dicts(rows)


def score_rows_for_catalogue(rows):
    score = 0

    for row in rows[:30]:
        joined = " ".join([normalise_key(cell) for cell in row if cell is not None])
        if "support item" in joined:
            score += 3
        if "price" in joined:
            score += 2
        if "registration group" in joined:
            score += 1

    return score


def rows_to_dicts(rows):
    header_index = find_header_row(rows)

    if header_index is None:
        frappe.throw(_("Could not find catalogue header row. Expected Support Item Number column."))

    headers = [clean_text(v) for v in rows[header_index]]
    data_rows = []

    for raw in rows[header_index + 1 :]:
        if not raw:
            continue

        item = {}
        for idx, header in enumerate(headers):
            if not header:
                continue
            item[header] = raw[idx] if idx < len(raw) else None

        if any(clean_text(v) for v in item.values()):
            data_rows.append(item)

    return data_rows


def find_header_row(rows):
    for idx, row in enumerate(rows[:40]):
        keys = [normalise_key(cell) for cell in row if cell is not None]
        compact = [normalise_compact(cell) for cell in row if cell is not None]

        has_support_item = (
            "support item number" in keys
            or "supportitemnumber" in compact
            or "support item" in keys
        )

        has_name_or_price = (
            "support item name" in keys
            or "supportitemname" in compact
            or "price limit" in keys
            or "pricelimit" in compact
            or "national" in keys
        )

        if has_support_item and has_name_or_price:
            return idx

    return None


def find_value(row, canonical_field):
    aliases = TEXT_ALIASES.get(canonical_field, [])
    normalised_row = {}
    compact_row = {}

    for header, value in row.items():
        normalised_row[normalise_key(header)] = value
        compact_row[normalise_compact(header)] = value

    for alias in aliases:
        k1 = normalise_key(alias)
        k2 = normalise_compact(alias)

        if k1 in normalised_row:
            return normalised_row[k1]

        if k2 in compact_row:
            return compact_row[k2]

    return None


def infer_service_type(support_item_number, support_item_name, support_category, registration_group):
    text = normalise_key(
        f"{support_item_number} {support_item_name} {support_category} {registration_group}"
    )

    if "supported independent living" in text or "sil" in text:
        return "SIL"

    if "specialist disability accommodation" in text or "sda" in text:
        return "SDA"

    if "support coordination" in text:
        return "Support Coordination"

    if "transport" in text or "travel" in text or "kilometre" in text or "kilometer" in text:
        return "Transport"

    if "sleepover" in text or "sleep over" in text:
        return "Sleepover"

    if "broken shift" in text:
        return "Broken Shift"

    if "community" in text or "social" in text or "centre based" in text:
        return "Community Participation"

    if "core" in text:
        return "Core Supports"

    return "Other"


def service_type_exists_or_other(value):
    if value and frappe.db.exists("NDIS Service Type", value):
        return value

    return "Other" if frappe.db.exists("NDIS Service Type", "Other") else None


def get_effective_price(row):
    price_limit = clean_money(find_value(row, "price_limit"))

    if price_limit:
        return price_limit

    price_candidates = [
        "price_national",
        "price_nsw",
        "price_vic",
        "price_qld",
        "price_sa",
        "price_wa",
        "price_tas",
        "price_act",
        "price_nt",
        "price_remote",
        "price_very_remote",
    ]

    for field in price_candidates:
        value = clean_money(find_value(row, field))
        if value:
            return value

    return 0


def set_if_field_exists(doc, fieldname, value):
    if frappe.get_meta(doc.doctype).has_field(fieldname):
        setattr(doc, fieldname, value)


def parse_catalogue_row(row, catalogue_version=None, effective_from=None, source_file=None):
    support_item_number = clean_text(find_value(row, "support_item_number"))
    support_item_name = clean_text(find_value(row, "support_item_name"))

    if not support_item_number or not support_item_name:
        return None

    support_category = clean_text(find_value(row, "support_category"))
    registration_group = clean_text(find_value(row, "registration_group"))
    unit = clean_text(find_value(row, "unit"))

    service_type = infer_service_type(
        support_item_number,
        support_item_name,
        support_category,
        registration_group,
    )

    price_limit = get_effective_price(row)

    parsed = {
        "support_item_number": support_item_number,
        "support_item_name": support_item_name,
        "support_category": support_category,
        "registration_group": registration_group,
        "unit": unit,
        "price_limit": price_limit,
        "price_national": clean_money(find_value(row, "price_national")),
        "price_nsw": clean_money(find_value(row, "price_nsw")),
        "price_vic": clean_money(find_value(row, "price_vic")),
        "price_qld": clean_money(find_value(row, "price_qld")),
        "price_sa": clean_money(find_value(row, "price_sa")),
        "price_wa": clean_money(find_value(row, "price_wa")),
        "price_tas": clean_money(find_value(row, "price_tas")),
        "price_act": clean_money(find_value(row, "price_act")),
        "price_nt": clean_money(find_value(row, "price_nt")),
        "price_remote": clean_money(find_value(row, "price_remote")),
        "price_very_remote": clean_money(find_value(row, "price_very_remote")),
        "quote_required": clean_bool(find_value(row, "quote_required")),
        "provider_travel_allowed": clean_bool(find_value(row, "provider_travel_allowed")),
        "non_face_to_face_allowed": clean_bool(find_value(row, "non_face_to_face_allowed")),
        "cancellation_allowed": clean_bool(find_value(row, "cancellation_allowed")),
        "ndia_requested_reports_allowed": clean_bool(find_value(row, "ndia_requested_reports_allowed")),
        "irregular_sil_allowed": clean_bool(find_value(row, "irregular_sil_allowed")),
        "gst_treatment": clean_gst_treatment(find_value(row, "gst_treatment")),
        "service_type": service_type_exists_or_other(service_type),
        "catalogue_version": catalogue_version,
        "effective_from": effective_from,
        "catalogue_source_file": source_file,
        "last_imported_on": now_datetime(),
        "active": 1,
    }

    parsed["is_sil"] = 1 if parsed["service_type"] == "SIL" else 0
    parsed["is_sda"] = 1 if parsed["service_type"] == "SDA" else 0
    parsed["is_group_support"] = 1 if "group" in normalise_key(support_item_name) else 0

    return parsed


def upsert_support_item(parsed, dry_run=0):
    existing_name = frappe.db.exists(
        "NDIS Support Item",
        {"support_item_number": parsed["support_item_number"]},
    )

    created = False

    if existing_name:
        doc = frappe.get_doc("NDIS Support Item", existing_name)
    else:
        doc = frappe.new_doc("NDIS Support Item")
        created = True

    for fieldname, value in parsed.items():
        set_if_field_exists(doc, fieldname, value)

    if dry_run:
        return "created" if created else "updated", doc.name or parsed["support_item_number"]

    doc.save(ignore_permissions=True)
    return "created" if created else "updated", doc.name


@frappe.whitelist()
def import_catalogue(
    file_path=None,
    file_url=None,
    file_docname=None,
    catalogue_version=None,
    effective_from=None,
    import_docname=None,
    dry_run=0,
    limit=None,
):
    """
    Import NDIS Support Catalogue from XLSX/CSV.

    Example:
    bench --site dev.localhost execute ndis_finance.services.catalogue_importer.import_catalogue --kwargs "{'file_path':'/path/to/file.xlsx','catalogue_version':'2025-26 v1.1','effective_from':'2025-11-24'}"
    """

    assert_action("manage_catalogue")

    dry_run = int(dry_run or 0)
    limit = int(limit or 0)

    path = get_physical_file_path(
        file_path=file_path,
        file_url=file_url,
        file_docname=file_docname,
    )

    if not os.path.exists(path):
        frappe.throw(_("File does not exist: {0}").format(path))

    source_file = os.path.basename(path)
    rows = load_rows_from_file(path)

    if limit:
        rows = rows[:limit]

    created_count = 0
    updated_count = 0
    skipped_count = 0
    warnings = []
    previews = []

    for idx, row in enumerate(rows, start=1):
        parsed = parse_catalogue_row(
            row,
            catalogue_version=catalogue_version,
            effective_from=effective_from,
            source_file=source_file,
        )

        if not parsed:
            skipped_count += 1
            continue

        try:
            action, name = upsert_support_item(parsed, dry_run=dry_run)

            if action == "created":
                created_count += 1
            else:
                updated_count += 1

            if dry_run and len(previews) < 10:
                previews.append(
                    {
                        "action": action,
                        "support_item_number": parsed.get("support_item_number"),
                        "support_item_name": parsed.get("support_item_name"),
                        "price_limit": parsed.get("price_limit"),
                        "service_type": parsed.get("service_type"),
                    }
                )

        except Exception as exc:
            skipped_count += 1
            warnings.append(f"Row {idx}: {str(exc)}")

    status = "Imported"
    if warnings:
        status = "Imported With Warnings"

    if import_docname and frappe.db.exists("NDIS Catalogue Import", import_docname):
        frappe.db.set_value(
            "NDIS Catalogue Import",
            import_docname,
            {
                "status": status if not dry_run else "Draft",
                "imported_on": now_datetime() if not dry_run else None,
                "total_rows": len(rows),
                "created_count": created_count,
                "updated_count": updated_count,
                "skipped_count": skipped_count,
                "warning_log": "\n".join(warnings[:200]),
            },
        )

    if not dry_run:
        frappe.db.commit()

    return {
        "dry_run": bool(dry_run),
        "file": path,
        "catalogue_version": catalogue_version,
        "effective_from": effective_from,
        "total_rows": len(rows),
        "created_count": created_count,
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "warnings": warnings[:20],
        "preview": previews,
    }


@frappe.whitelist()
def quick_check_support_items(limit=10):
    data = frappe.get_all(
        "NDIS Support Item",
        fields=[
            "name",
            "support_item_number",
            "support_item_name",
            "service_type",
            "price_limit",
            "gst_treatment",
            "catalogue_version",
        ],
        limit=int(limit or 10),
        order_by="modified desc",
    )

    return data
