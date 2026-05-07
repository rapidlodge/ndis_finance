import os

import frappe


PHASE1I_JS_FILES = [
    "public/js/ndis_claim_batch.js",
    "public/js/ndis_claim_batch_list.js",
    "public/js/ndis_claim_line.js",
    "public/js/ndis_claim_line_list.js",
    "public/js/ndis_payment_reconciliation_batch.js",
    "public/js/ndis_payment_reconciliation_batch_list.js",
    "public/js/ndis_funding_leakage_register.js",
    "public/js/ndis_funding_leakage_register_list.js",
    "public/js/ndis_recovery_case.js",
    "public/js/ndis_recovery_case_list.js",
]

FORM_HOOK_DOCTYPES = [
    "NDIS Claim Batch",
    "NDIS Claim Line",
    "NDIS Payment Reconciliation Batch",
    "NDIS Funding Leakage Register",
    "NDIS Recovery Case",
]


@frappe.whitelist()
def health_check():
    app_path = frappe.get_app_path("ndis_finance")
    app_root = os.path.dirname(app_path)

    files = {
        rel_path: os.path.exists(os.path.join(app_root, "ndis_finance", rel_path))
        for rel_path in PHASE1I_JS_FILES
    }

    hooks = frappe.get_hooks()
    doctype_js = hooks.get("doctype_js", {})
    doctype_list_js = hooks.get("doctype_list_js", {})

    return {
        "js_files": files,
        "doctype_js_hooks": {
            doctype: doctype in doctype_js
            for doctype in FORM_HOOK_DOCTYPES
        },
        "doctype_list_js_hooks": {
            doctype: doctype in doctype_list_js
            for doctype in FORM_HOOK_DOCTYPES
        },
    }
