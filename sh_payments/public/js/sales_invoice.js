frappe.ui.form.on("Sales Invoice", {
  // 1. Set the filter when the form loads and on refresh
  refresh: function (frm) {
    set_item_filter(frm);
  },

  // 2. Re-apply the filter when the Company field is changed
  company: function (frm) {
    set_item_filter(frm);
    // Clear the items grid to prompt the user to re-select items
    // This is important to ensure previously selected items from a different company are cleared.
    if (frm.doc.items && frm.doc.items.length) {
      // Using frm.clear_table is the standard way to clear a child table
      frm.clear_table("items");
      frm.refresh_field("items");
    }
  },
});

var set_item_filter = function (frm) {
  // Get the name of the Company selected in the Sales Invoice
  var selected_company = frm.doc.company;

  frm.set_query("item_code", "items", function (doc, cdt, cdn) {
    var filters = [
      // Standard ERPNext filter to only show items marked as 'Is Sales Item'
      ["Item", "is_sales_item", "=", "1"],
    ];

    if (selected_company) {
      // Filter the Item by its Item Group, which should match the Company name.
      filters.push(["Item", "item_group", "=", selected_company]);
    }

    return {
      filters: filters,
    };
  });
};
